#!/usr/bin/env python3
"""Tests RM3033 — mmi-pm.py : résolution `<cmd>` et repli `<nom> <verbe>` → pm-<nom>-<verbe>, alias par nom d'appel (mmi-<domaine>),
--list (filtré), exécution transparente (subprocess sur un faux dossier de scripts via PM_CORE_DIR)."""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mmi_pm", HERE / "mmi-pm.py"); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


check("argv_for : mmi-pm inchangé", M.argv_for("/usr/local/bin/mmi-pm", ["core", "update"]) == ["core", "update"] and M.argv_for("mmi-pm.py", ["x"]) == ["x"])
check("argv_for : mmi-<domaine> préfixe", M.argv_for("/usr/local/bin/mmi-core", ["update", "--dry-run"]) == ["core-update", "--dry-run"] and M.argv_for("mmi-task", ["show", "42"]) == ["task-show", "42"])
check("argv_for : mmi-<domaine> seul → liste du domaine", M.argv_for("mmi-task", []) == ["--list", "task"] and M.argv_for("mmi-env", ["--help"]) == ["--list", "env"])
t, r = M.resolve("core", ["update", "--dry-run"]); check("repli nom verbe → pm-core-update.py, verbe consommé", t.name == "pm-core-update.py" and r == ["--dry-run"])
t, r = M.resolve("task-show", ["42"]); check("cmd direct → pm-task-show.py, args intacts", t.name == "pm-task-show.py" and r == ["42"])
# RM3142 : `index` appartient désormais à l'index de REQUÊTAGE (RM3128) ; l'annuaire des projets,
# qui portait ce nom avant, est devenu `projects-index`. RM3128 avait écrasé son module sans le voir,
# et ses quatre commandes appelaient depuis des fonctions disparues — mortes sans un mot.
t, r = M.resolve("index", ["add", "a/b"]); check("index <verbe> → pm-index.py, verbe passé en argument", t.name == "pm-index.py" and r == ["add", "a/b"])
t, r = M.resolve("projects-index", ["add", "a/b"]); check("projects-index add → pm-projects-index-add.py", t.name == "pm-projects-index-add.py" and r == ["a/b"])
t, r = M.resolve("index", ["rebuild"]); check("index rebuild → l'index de requêtage, sans ambiguïté possible", t.name == "pm-index.py" and r == ["rebuild"])

# la garde : deux scripts ne doivent pas se disputer un domaine. `pm-<x>.py` ET `pm-<x>-<v>.py`
# ensemble, c'est un `<v>` qui peut être lu comme un sous-verbe de l'un OU comme un script à part —
# et le dispatch tranche en silence. La liste blanche dit « on sait, et il n'y a pas d'homonyme ».
COHABITENT = {"cdc", "notify"}      # pm-cdc/pm-cdc-features, pm-notify/pm-notify-mail : aucun verbe commun
_S = pathlib.Path(__file__).resolve().parent
_simples = {q.stem[3:] for q in _S.glob("pm-*.py") if q.stem.count("-") == 1}
_disputes = sorted(d for d in _simples if list(_S.glob(f"pm-{d}-*.py")) and d not in COHABITENT)
check("aucun domaine partagé entre un script simple et des scripts composés (RM3142)", not _disputes, str(_disputes))
check("inconnu → None", M.resolve("zz", ["x"]) == (None, ["x"]) and M.resolve("core", ["--dry-run"]) == (None, ["--dry-run"]))
cmds = M._list_commands(); check("--list voit les verbes portés", all(c in cmds for c in ("core-update", "projects-index-add", "projects-index-remove", "projects-index-rebuild", "projects-index-list", "env-vhost", "task-add")))

with tempfile.TemporaryDirectory() as td:
    core = pathlib.Path(td); sc = core / "scripts"; sc.mkdir()
    (sc / "pm-demo-run.py").write_text("import sys; print('demo-run', *sys.argv[1:])\n")
    (sc / "pm-solo.py").write_text("import sys; print('solo', *sys.argv[1:])\n")
    (sc / "pm-other").write_text("#!/bin/sh\necho other \"$@\"\n"); os.chmod(sc / "pm-other", 0o755)
    env = dict(os.environ, PM_CORE_DIR=str(core))
    run = lambda *a: subprocess.run([sys.executable, str(HERE / "mmi-pm.py"), *a], capture_output=True, text=True, env=env)  # noqa: E731
    check("exécution directe", run("demo-run", "a", "b").stdout.strip() == "demo-run a b")
    check("exécution par repli « nom verbe »", run("demo", "run", "--x").stdout.strip() == "demo-run --x")
    check("script sans extension", run("other", "1").stdout.strip() == "other 1")
    r = run("nope"); check("inconnu : code 1 + message", r.returncode == 1 and "sous-commande inconnue 'nope'" in r.stderr)
    check("--list et --list <domaine>", run("--list").stdout.split() == ["demo-run", "other", "solo"] and run("--list", "demo").stdout.split() == ["demo-run"])
    alias = core / "mmi-demo"; alias.symlink_to(HERE / "mmi-pm.py")
    r = subprocess.run([sys.executable, str(alias), "run", "z"], capture_output=True, text=True, env=env)
    check("alias mmi-demo run → demo-run", r.stdout.strip() == "demo-run z", r.stdout + r.stderr)
    check("alias mmi-demo seul → liste du domaine", subprocess.run([sys.executable, str(alias)], capture_output=True, text=True, env=env).stdout.split() == ["demo-run"])

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — dispatcher mmi-pm (RM3033)")
