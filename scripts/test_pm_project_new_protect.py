"""Tests RM2057 — la protection des branches est posée à la CRÉATION du projet.

Sans réseau : `pm-protect` et `git remote` sont simulés, on vérifie ce que
pm-project-new décide d'appeler — quels dépôts, dans quel ordre, et surtout que
rien de tout cela ne peut faire échouer la création du projet.

Lancer : python3 scripts/test_pm_project_new_protect.py
"""
import importlib.util
import io
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_project_new", str(_HERE / "pm-project-new.py"))
ppn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ppn)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


class FakeProc:
    def __init__(self, rc=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = rc, stdout, stderr


def make_ws(root: Path) -> Path:
    ws = root / "monprojet"
    (ws / ".mmi-pm" / "tasks").mkdir(parents=True)
    (ws / "repos" / "monprojet-code.git").mkdir(parents=True)
    (ws / "repos" / "scratch.git").mkdir(parents=True)
    return ws


def run_with(ws, protect_rc=0):
    """Joue protect_project_repos avec un faux pm-protect ; rend (appels, sorties)."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append([str(c) for c in cmd])
        if "remote" in cmd:
            # seul monprojet-code.git a un remote GitLab
            repo = str(cmd[2])
            if repo.endswith("monprojet-code.git"):
                return FakeProc(0, "gitlab:iprospective/monprojet-code.git\n")
            return FakeProc(2, "", "No such remote 'origin'")
        return FakeProc(protect_rc, "  ✓ main     push=personne  merge=Maintainer\n",
                        "  ✗ main     échec (HTTP 403)" if protect_rc else "")

    real = ppn.subprocess.run
    ppn.subprocess.run = fake_run
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            ppn.protect_project_repos(ws, False)
    finally:
        ppn.subprocess.run = real
    return calls, out.getvalue(), err.getvalue()


tmp = Path(tempfile.mkdtemp(prefix="rm2057-"))
ws = make_ws(tmp)

calls, out, err = run_with(ws)
protects = [c for c in calls if any("pm-protect.py" in x for x in c)]
repos = [c[c.index("--repo") + 1] for c in protects]

check("le core est protégé (le workspace lui-même)", repos and repos[0] == str(ws))
check("le dépôt de code avec remote GitLab est protégé",
      str(ws / "repos" / "monprojet-code.git") in repos)
check("un dépôt sans remote GitLab est ignoré (rien à résoudre)",
      str(ws / "repos" / "scratch.git") not in repos)
check("aucune politique forcée : pm-protect détecte core vs code",
      not any("--core" in c or "--no-core" in c for c in protects))
check("le résultat de pm-protect est montré à l'écran", "push=personne" in out)

# l'échec ne doit RIEN casser : un projet créé sans protection reste créé
calls, out, err = run_with(ws, protect_rc=1)
check("un échec de protection ne lève pas", True)          # on est arrivé ici
check("l'échec est annoncé", "non posée" in err)
check("l'échec donne la commande de rattrapage", "pm-protect.py --repo" in err)
check("l'échec dit que le projet reste créé", "reste créé" in err)

# dry-run : on annonce, on ne pose rien
calls = []


def fake_run_dry(cmd, **kw):
    calls.append(cmd)
    return FakeProc(0, "", "")


real = ppn.subprocess.run
ppn.subprocess.run = fake_run_dry
out = io.StringIO()
try:
    with redirect_stdout(out):
        ppn.protect_project_repos(ws, True)
finally:
    ppn.subprocess.run = real
check("dry-run : annonce la protection", "protégerait" in out.getvalue())
check("dry-run : n'appelle PAS pm-protect",
      not any("pm-protect.py" in str(c) for c in calls))

# le câblage lui-même : la création appelle bien l'étape, après la publication du core
src = (_HERE / "pm-project-new.py").read_text(encoding="utf-8")
pub = src.index("publication du repo -core échouée")
call = src.index("protect_project_repos(workspace, False)")
check("l'étape est câblée dans la création", call > pub)
check("elle vient APRÈS la publication (sinon la branche n'existe pas encore)",
      call - pub < 400)

import shutil
shutil.rmtree(tmp, ignore_errors=True)
print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
