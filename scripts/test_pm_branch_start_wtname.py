#!/usr/bin/env python3
"""Nommage du worktree de session par pm-branch-start (RM2523).

Le nom dérivait de `root.name`, c'est-à-dire du worktree **courant**. Lancer
`pm-branch-start --worktree` depuis le worktree d'un autre ticket concaténait
donc son nom, et le suivant recommençait :

    envs/<repo>-dev-2394-s29
    envs/<repo>-dev-2394-s29-2431-s29
    envs/<repo>-rm2356-2373-s1-2385-s1-2323-s20-2355-s20-2519-s20-2515-s20

(7 cas constatés sur le workspace PM en août 2026.)

Convention unique retenue, alignée sur `pm-env-session create` :
    envs/<repo>-rm<id>          canonique
    envs/<repo>-rm<id>-s<seq>   uniquement si le canonique sert une AUTRE branche

Lancement : python3 scripts/test_pm_branch_start_wtname.py
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("pm_branch_start", HERE / "pm-branch-start.py")
pbs = importlib.util.module_from_spec(_spec)
sys.modules["pm_branch_start"] = pbs
_spec.loader.exec_module(pbs)

FAILURES = []


def check(label, got, want):
    if got == want:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label} : attendu {want!r}, obtenu {got!r}")
        FAILURES.append(label)


def git(*a, cwd=None):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


def build(tmp, repo="myrepo"):
    """Layout RM1993 : repos/<repo>.git + envs/<repo>-dev (worktree d'intégration)."""
    ws = tmp / "ws"
    (ws / "envs").mkdir(parents=True)
    bare = ws / "repos" / f"{repo}.git"
    bare.parent.mkdir()
    git("init", "-q", "--bare", str(bare))
    seed = tmp / "seed"
    git("clone", "-q", str(bare), str(seed))
    git("config", "user.email", "t@t", cwd=seed)
    git("config", "user.name", "t", cwd=seed)
    (seed / "f.txt").write_text("x\n")
    git("add", "-A", cwd=seed)
    git("commit", "-qm", "seed", cwd=seed)
    git("push", "-q", "origin", "HEAD:refs/heads/dev", cwd=seed)
    integ = ws / "envs" / f"{repo}-dev"
    git("-C", str(bare), "worktree", "add", "-q", str(integ), "dev")
    return ws, bare, integ


def test_nom_depuis_le_repo():
    print("Nom dérivé du REPO, pas du worktree courant :")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ws, bare, integ = build(t)

        check("repo_name_of depuis l'env d'intégration", pbs.repo_name_of(integ), "myrepo")
        p = pbs.worktree_path(integ, 2523, "2523-x-m1-s45", 45)
        check("nom canonique", p.name, "myrepo-rm2523")

        # le cas qui produisait l'empilement : on lance depuis le worktree d'un
        # AUTRE ticket, dont le nom contient déjà un suffixe
        other = ws / "envs" / "myrepo-rm2394-s29"
        git("-C", str(bare), "worktree", "add", "-q", "-b", "2394-y", str(other), "dev")
        check("repo_name_of depuis un worktree de ticket", pbs.repo_name_of(other), "myrepo")
        p2 = pbs.worktree_path(other, 2431, "2431-z-m1-s29", 29)
        check("pas d'empilement de suffixes", p2.name, "myrepo-rm2431")


def test_collision():
    print("Collision sur le canonique :")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ws, bare, integ = build(t)
        # le canonique existe déjà, sur une AUTRE branche
        taken = ws / "envs" / "myrepo-rm2523"
        git("-C", str(bare), "worktree", "add", "-q", "-b", "2523-deja-la", str(taken), "dev")

        p = pbs.worktree_path(integ, 2523, "2523-autre-session-m1-s7", 7)
        check("suffixe de session ajouté", p.name, "myrepo-rm2523-s7")

        # même branche → on réutilise le canonique au lieu d'en créer un second
        p2 = pbs.worktree_path(integ, 2523, "2523-deja-la", 7)
        check("même branche → canonique réutilisé", p2.name, "myrepo-rm2523")


def test_depot_classique():
    """Hors layout RM1993 (dépôt avec .git classique), on ne casse rien."""
    print("Dépôt classique (hors layout envs/repos) :")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        d = t / "projet"
        d.mkdir()
        git("init", "-q", str(d))
        check("nom = dossier du dépôt", pbs.repo_name_of(d), "projet")


if __name__ == "__main__":
    test_nom_depuis_le_repo()
    test_collision()
    test_depot_classique()
    if FAILURES:
        print(f"\n{len(FAILURES)} échec(s) : {', '.join(FAILURES)}")
        sys.exit(1)
    print("\nTous les tests passent.")
