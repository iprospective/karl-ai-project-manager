#!/usr/bin/env python3
"""Tests RM2394 — résolution du worktree d'un ticket PAR BRANCHE.

Régression du blocage constaté en recette RM2386 : un ticket pris avec
`pm-branch-start --worktree` monte un worktree au nom discriminé par session
(RM2034, `<repo>-dev-<id>-s<seq>`), mais les outils d'env de test devinaient le
chemin canonique `<repo>-rm<id>` et échouaient (`worktree add` rc=128 /
« worktree absent »). Le fix : résoudre par la branche `<id>-*` via
`git worktree list`, quel que soit le nom du worktree.

Utilise un VRAI dépôt git temporaire (git worktree list doit fonctionner).
Lancer : python3 scripts/test_pm_env_session_worktree.py
"""
import importlib.util
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def _load(modname, filename):
    spec = importlib.util.spec_from_file_location(modname, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


pes = _load("pm_env_session", "pm-env-session.py")
cte = _load("cte", "pm-cockpit-test-env.py")

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def g(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} → {r.stderr}")
    return r.stdout


# — dépôt réel : seed → bare demo.git → worktrees ——————————————————————————
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2394-"))
seed = tmp / "seed"
seed.mkdir()
g("init", "-q", "-b", "main", cwd=seed)
g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
  "--allow-empty", "-m", "seed", cwd=seed)
ws = tmp / "ws"
(ws / ".mmi-pm").mkdir(parents=True)
(ws / ".mmi-pm" / "meta.yml").write_text("repos:\n- name: demo\n")
(ws / "envs").mkdir()
bare = ws / "repos" / "demo.git"
bare.parent.mkdir(parents=True)
g("clone", "-q", "--bare", str(seed), str(bare))

RMID = 2394


def add_wt(dirname, branch):
    path = ws / "envs" / dirname
    g("-C", str(bare), "worktree", "add", "-q", "-b", branch, str(path), "main")
    return path


# 1. bare non initialisé → aucun worktree, pas d'erreur (résilience)
check("bare vide → None (pas de die)",
      pes.worktree_for_branch(ws / "repos" / "absent.git", "demo", RMID) is None)

# 2. aucun worktree du ticket → None
check("aucun worktree ticket → None",
      pes.worktree_for_branch(bare, "demo", RMID) is None)

# 3. worktree au nom DISCRIMINÉ (RM2034) → résolu par branche
disc = add_wt(f"demo-dev-{RMID}-s5", f"{RMID}-ma-tache-m1-s5")
res = pes.worktree_for_branch(bare, "demo", RMID)
check("worktree discriminé résolu par branche",
      res is not None and res[0] == disc and res[1] == f"{RMID}-ma-tache-m1-s5")

# 4. ajout d'un worktree au nom CANONIQUE → priorité au canonique
canon = add_wt(f"demo-rm{RMID}", f"{RMID}-canonique")
res = pes.worktree_for_branch(bare, "demo", RMID)
check("nom canonique prioritaire à égalité", res is not None and res[0] == canon)

# 5. un autre ticket ne matche pas (pas de faux positif de préfixe)
other = add_wt("demo-dev-239-s1", "239-autre")
res = pes.worktree_for_branch(bare, "demo", 239)
check("ticket 239 ≠ 2394 (préfixe strict)", res is not None and res[0] == other)
check("2394 ne capte pas 239", pes.worktree_for_branch(bare, "demo", RMID)[0] == canon)

# 6. list_worktrees : le bare + worktrees, branche parsée
wts = dict((p.name, b) for p, b in pes.list_worktrees(bare))
check("list_worktrees parse la branche",
      wts.get(f"demo-rm{RMID}") == f"{RMID}-canonique")

# 7. pm-cockpit-test-env.resolve_worktree résout le DISCRIMINÉ (RM2394).
#    On retire le worktree canonique pour ne laisser que le discriminé, et on
#    y pose un stub karl-agent.py (le seul worktree cockpit-testable du ticket).
g("-C", str(bare), "worktree", "remove", "--force", str(canon))
(disc / "scripts").mkdir(parents=True, exist_ok=True)
(disc / "scripts" / "karl-agent.py").write_text("# stub\n")
check("cockpit resolve_worktree trouve le discriminé",
      cte.resolve_worktree(ws, RMID) == disc)

# 8. cmd_create RÉUTILISE le worktree existant → AUCUN `git worktree add`
#    (le blocage d'origine : worktree add rc=128 « branch already used »).
#    Repo sans bloc runtime (comme le repo PM) : create s'arrête en « code seul ».
import types  # noqa: E402

git_calls = []
_real_git = pes.git
pes.git = lambda a, cwd=None, check=True: git_calls.append(list(a)) or _real_git(a, cwd, check)
pes.load_env_runtime_cfg = lambda: {"ssh_host": "x", "helper": "y"}
pes.pm_session = types.SimpleNamespace(record_worktree=lambda *a: None,
                                       record_branch=lambda *a: None)
create_args = types.SimpleNamespace(
    rmid=RMID, workspace=str(ws), repo=None, slug=None,
    db_clone=False, no_db_clone=False, no_vhost=False, dry_run=False)
pes.cmd_create(create_args)
pes.git = _real_git
added = [c for c in git_calls if "worktree" in c and "add" in c]
check("cmd_create réutilise le worktree (aucun `git worktree add`)", not added)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests RM2394 (résolution worktree par branche) passent")
