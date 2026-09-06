"""Tests RM3016 — pm-repo-new sur GitHub, sans réseau : la forge et git sont simulés, on vérifie
ce que le script DÉCIDE d'appeler (owner par lecture, refus si le dépôt existe, POST sur l'org
ou l'utilisateur, push des branches choisies sur le remote choisi, défaut fixé, protection qui
n'échoue jamais la création).

Lancer : python3 scripts/test_pm_repo_new_github.py
"""
import importlib.util, io, sys, tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_repo_new", str(_HERE / "pm-repo-new.py"))
prn = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(prn)
fails = []
def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond: fails.append(name)

class FakeForge:
    def __init__(self, reponses): self.reponses = reponses; self.appels = []
    def api(self, method, path, token, fields=None):
        self.appels.append((method, path, fields))
        for (m, p), rep in self.reponses.items():
            if m == method and path.startswith(p): return rep
        return 404, {"message": "Not Found"}, "{}"

class Args:
    def __init__(self, **k):
        self.visibility = "private"; self.description = "AtomBox"; self.default_branch = "main"
        self.push_from = None; self.no_protect = False; self.porcelain = False; self.dry_run = False; self.remote = "github"
        self.__dict__.update(k)

# 1. owner : organisation, puis utilisateur, puis introuvable
f = FakeForge({("GET", "/orgs/iprospective"): (200, {"login": "iprospective"}, "")})
check("owner organisation", prn.gh_owner(f, "t", "iprospective") == "org")
f = FakeForge({("GET", "/users/mathieu"): (200, {"login": "mathieu"}, "")})
check("owner utilisateur", prn.gh_owner(f, "t", "mathieu") == "user")
try:
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()): prn.gh_owner(FakeForge({}), "t", "nul")
    check("owner introuvable → refus", False)
except SystemExit: check("owner introuvable → refus", True)

# 2. existence : 200 = existe, 404 = libre, autre = refus
check("dépôt libre (404)", prn.gh_repo_exists(FakeForge({}), "t", "iprospective/atombox") is None)
check("dépôt existant (200)", prn.gh_repo_exists(FakeForge({("GET", "/repos/iprospective/atombox"): (200, {"full_name": "iprospective/atombox"}, "")}), "t", "iprospective/atombox") is not None)

# 3. création : sur l'organisation, privé par défaut, sans auto_init
f = FakeForge({("POST", "/orgs/iprospective/repos"): (201, {"id": 1, "full_name": "iprospective/atombox", "html_url": "https://github.com/iprospective/atombox"}, "")})
r = prn.gh_create(f, "t", "iprospective", "org", "atombox", Args())
m, p, champs = f.appels[-1]
check("POST /orgs/{org}/repos", p == "/orgs/iprospective/repos" and champs["private"] is True and champs["auto_init"] is False and champs["name"] == "atombox")
f = FakeForge({("POST", "/user/repos"): (201, {"id": 2, "full_name": "mathieu/x"}, "")})
prn.gh_create(f, "t", "mathieu", "user", "x", Args(visibility="public"))
check("POST /user/repos pour un utilisateur, public", f.appels[-1][1] == "/user/repos" and f.appels[-1][2]["private"] is False)

# 4. push : alias github:, branches choisies, remote nommé — sans jamais toucher origin
appels = []
class FakeProc:
    def __init__(self, rc=0): self.returncode = rc; self.stdout = ""; self.stderr = ""
prn.subprocess.run = lambda cmd, **k: (appels.append(cmd), FakeProc())[1]
with tempfile.TemporaryDirectory() as d:
    Path(d, "HEAD").write_text("ref: refs/heads/main\n")
    with redirect_stdout(io.StringIO()):
        prn.push_from(d, "iprospective/atombox", "main", False, "github", ["dev", "main"], "github")
check("remote github: posé sous le nom « github », origin intact", appels[0][-2:] == ["remove", "github"] and appels[1][-2:] == ["github", "github:iprospective/atombox.git"])
check("push de main et dev seulement, plus les tags", appels[2][-4:] == ["main", "dev", "--tags"] and appels[2][-5] == "github")

# 5. protection : refusée par le plan → avertissement, jamais une exception
f = FakeForge({("PUT", "/repos/iprospective/atombox/branches/main/protection"): (403, {"message": "Upgrade to GitHub Pro"}, "{}")})
with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
    ok = prn.gh_protect(f, "t", "iprospective/atombox", "main", False)
check("protection refusée (403) → avertissement, pas d'échec", ok is False)
f = FakeForge({("PUT", "/repos/iprospective/atombox/branches/main/protection"): (200, {}, "{}")})
with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
    check("protection posée (200)", prn.gh_protect(f, "t", "iprospective/atombox", "main", False) is True)

print("\n%d échec(s)" % len(fails)); sys.exit(1 if fails else 0)
