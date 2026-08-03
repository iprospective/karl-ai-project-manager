#!/usr/bin/env python3
"""Tests de la résolution du worktree par `pm-env-session teardown` (RM2523).

Le bug : `teardown` devinait le chemin `envs/<repo>-rm<id>` au lieu d'utiliser la
résolution par branche déjà en place dans `create` (RM2394). Tous les worktrees
créés par `pm-branch-start --worktree` — nommés `<repo>-dev-<id>-s<seq>` — étaient
donc ignorés, avec un message « worktree déjà absent » et un code de sortie 0 :
un faux négatif silencieux, qui court-circuitait au passage les gardes « worktree
sale » et « commits non poussés ».

On monte un vrai workspace minimal (bare + worktree au nommage NON canonique) et
on vérifie le comportement de bout en bout.

Lancement : python3 scripts/test_pm_env_session_teardown_resolve.py
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("pm_env_session", HERE / "pm-env-session.py")
pes = importlib.util.module_from_spec(_spec)
sys.modules["pm_env_session"] = pes
_spec.loader.exec_module(pes)

FAILURES = []


def check(label, got, want):
    if got == want:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label} : attendu {want!r}, obtenu {got!r}")
        FAILURES.append(label)


def git(*a, cwd=None):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


def build_ws(tmp, repo="myrepo", wt_name=None, branch=None):
    """Workspace layout RM1993 : .mmi-pm/meta.yml + repos/<repo>.git + envs/."""
    ws = tmp / "ws"
    (ws / ".mmi-pm").mkdir(parents=True)
    (ws / ".mmi-pm" / "meta.yml").write_text(
        f"repos:\n- name: {repo}\n  integration_branch: dev\n", encoding="utf-8")
    (ws / "envs").mkdir()
    bare = ws / "repos" / f"{repo}.git"
    bare.parent.mkdir()
    git("init", "-q", "--bare", str(bare))

    # un commit initial via un clone jetable, puis le worktree de session
    seed = tmp / "seed"
    git("clone", "-q", str(bare), str(seed))
    git("config", "user.email", "t@t", cwd=seed)
    git("config", "user.name", "t", cwd=seed)
    (seed / "f.txt").write_text("x\n")
    git("add", "-A", cwd=seed)
    git("commit", "-qm", "seed", cwd=seed)
    git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=seed)

    if wt_name and branch:
        wt = ws / "envs" / wt_name
        git("-C", str(bare), "worktree", "add", "-q", "-b", branch, str(wt), "main")
        # Brancher un remote et pousser : sans ça, la garde « commits non
        # poussés » (RM2319) refuse le teardown. Elle est légitime — et n'était
        # jamais atteinte avant ce correctif, faute de worktree résolu.
        git("-C", str(wt), "remote", "add", "origin", str(bare))
        git("-C", str(wt), "push", "-q", "-u", "origin", branch)
    return ws, bare


def test_resolution_nommage_non_canonique():
    """Le worktree de pm-branch-start (`-dev-<id>-s<seq>`) doit être trouvé."""
    print("Résolution d'un worktree au nommage non canonique :")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ws, bare = build_ws(t, wt_name="myrepo-dev-2523-s45",
                            branch="2523-fix-teardown-m1-s45")
        found = pes.worktree_for_branch(bare, "myrepo", 2523)
        check("worktree trouvé", found is not None, True)
        if found:
            check("bon chemin", found[0].name, "myrepo-dev-2523-s45")
            check("bonne branche", found[1], "2523-fix-teardown-m1-s45")
        # le chemin canonique, lui, n'existe pas : c'est tout le sujet
        check("le chemin canonique n'existe pas",
              (ws / "envs" / "myrepo-rm2523").exists(), False)


def test_aucun_worktree():
    """Ticket sans worktree monté → pas de faux positif."""
    print("Ticket sans worktree :")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        _, bare = build_ws(t)
        check("aucun worktree résolu", pes.worktree_for_branch(bare, "myrepo", 9999), None)


def test_canonique_prioritaire():
    """À égalité, le nom canonique gagne (chemin stable pour vhost/URL)."""
    print("Priorité au nom canonique :")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ws, bare = build_ws(t, wt_name="myrepo-dev-2523-s45",
                            branch="2523-fix-teardown-m1-s45")
        git("-C", str(bare), "worktree", "add", "-q", "-b", "2523-autre",
            str(ws / "envs" / "myrepo-rm2523"), "main")
        found = pes.worktree_for_branch(bare, "myrepo", 2523)
        check("le canonique l'emporte", found[0].name if found else None, "myrepo-rm2523")


def test_teardown_bout_en_bout():
    """teardown --dry-run doit ANNONCER le bon worktree, pas « déjà absent »."""
    print("teardown de bout en bout (dry-run) :")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ws, _ = build_ws(t, wt_name="myrepo-dev-2523-s45",
                         branch="2523-fix-teardown-m1-s45")

        class Args:
            rmid, workspace, repo = 2523, str(ws), None
            dry_run, force, keep_db = True, False, False

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        # set_test_url touche Redmine : neutralisé, hors périmètre du test.
        original = pes.set_test_url
        pes.set_test_url = lambda *a, **k: None
        try:
            with redirect_stdout(buf):
                pes.cmd_teardown(Args())
        finally:
            pes.set_test_url = original
        out = buf.getvalue()
        check("le worktree non canonique est annoncé",
              "myrepo-dev-2523-s45" in out, True)
        check("plus de « déjà absent »", "déjà absent" in out, False)
        check("la branche résolue est affichée",
              "2523-fix-teardown-m1-s45" in out, True)


if __name__ == "__main__":
    test_resolution_nommage_non_canonique()
    test_aucun_worktree()
    test_canonique_prioritaire()
    test_teardown_bout_en_bout()
    if FAILURES:
        print(f"\n{len(FAILURES)} échec(s) : {', '.join(FAILURES)}")
        sys.exit(1)
    print("\nTous les tests passent.")
