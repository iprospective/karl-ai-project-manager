#!/usr/bin/env python3
"""RM2754 — `git.worktree` renseigné quand le dépôt cible est un worktree lié.

Le garde-fou phare de RM2240 (« tu commites depuis le mauvais worktree ») compare
le worktree courant au champ `git.worktree` du frontmatter. Or ce champ n'était
écrit que par `pm-branch-start --worktree`, alors que le flux normal passe par
`pm-task-take`, qui crée l'env de session puis appelle `pm-branch-start --repo
<env>` SANS `--worktree` : le champ restait vide pour tous les tickets pris
normalement, donc le contrôle n'avait rien à comparer.

Ce qui est vérifié ici :
  - la détection est un FAIT git (deux chemins comparés), pas une heuristique sur
    le nom du dossier — testée contre de vrais dépôts, pas seulement en unitaire ;
  - le mode in-place dans le dépôt principal ne renseigne toujours rien.

Lancer : python3 scripts/test_pm_branch_start_worktree.py
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


def dirs(root):
    """(git-dir, git-common-dir) absolus, comme les lit pm-branch-start."""
    return (git("-C", str(root), "rev-parse", "--path-format=absolute",
                "--git-dir").stdout.strip(),
            git("-C", str(root), "rev-parse", "--path-format=absolute",
                "--git-common-dir").stdout.strip())


def test_unitaire():
    print("is_linked_worktree — fonction pure :")
    check("chemins identiques → dépôt principal",
          pbs.is_linked_worktree("/r/.git", "/r/.git"), False)
    check("git-dir sous worktrees/ → worktree lié",
          pbs.is_linked_worktree("/r/repos/x.git/worktrees/x-rm1", "/r/repos/x.git"), True)
    check("chemin manquant → on n'invente rien",
          pbs.is_linked_worktree("", "/r/.git"), False)
    check("chemin manquant (l'autre) → idem",
          pbs.is_linked_worktree("/r/.git", ""), False)
    check("écritures équivalentes du même chemin → pas de faux positif",
          pbs.is_linked_worktree("/r/./.git", "/r/.git"), False)


def test_vrais_depots():
    """Contre de VRAIS dépôts : c'est git qui doit distinguer les deux cas."""
    print("Détection contre de vrais dépôts :")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        # layout RM1993 : repos/<repo>.git (bare) + envs/<repo>-dev + envs/<repo>-rm<id>
        ws = t / "ws"
        (ws / "envs").mkdir(parents=True)
        bare = ws / "repos" / "myrepo.git"
        bare.parent.mkdir()
        git("init", "-q", "--bare", str(bare))
        seed = t / "seed"
        git("clone", "-q", str(bare), str(seed))
        git("config", "user.email", "t@t", cwd=seed)
        git("config", "user.name", "t", cwd=seed)
        (seed / "f.txt").write_text("x\n")
        git("add", "f.txt", cwd=seed)
        git("commit", "-qm", "seed", cwd=seed)
        git("push", "-q", "origin", "HEAD:refs/heads/dev", cwd=seed)

        env = ws / "envs" / "myrepo-rm2754"
        git("-C", str(bare), "worktree", "add", "-q", "-b", "2754-x", str(env), "dev")
        check("env de session (worktree lié) → détecté",
              pbs.is_linked_worktree(*dirs(env)), True)
        check("clone classique (dépôt principal) → non détecté",
              pbs.is_linked_worktree(*dirs(seed)), False)

        # …et le cas qui a produit le bug : le nom du dossier ne dit RIEN. Un
        # worktree lié hors de `envs/` doit être détecté quand même.
        ailleurs = t / "pas-dans-envs"
        git("-C", str(bare), "worktree", "add", "-q", "-b", "2754-y", str(ailleurs), "dev")
        check("worktree lié hors de envs/ → détecté quand même",
              pbs.is_linked_worktree(*dirs(ailleurs)), True)


TACHE = """---
redmine_id: 9999
title: ticket de test
status: en_cours
git:
  repo: myrepo
  branch: 9999-x
{worktree}updated: 2026-08-20T00:00
---
## Contexte
"""


def test_garde_pre_commit():
    """La garde n°2 de RM2240 doit RÉELLEMENT refuser — et être inerte sans le champ.

    C'est le cœur du bug : le contrôle ne refusait rien, non parce qu'il était
    faux, mais parce que le champ qu'il compare n'était jamais écrit.
    """
    print("Garde `pm-pre-commit` n°2 (mauvais worktree) :")
    hook = HERE / "pm-pre-commit.py"
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ws = t / "ws"
        (ws / ".mmi-pm" / "tasks").mkdir(parents=True)
        (ws / "envs").mkdir()
        bare = ws / "repos" / "myrepo.git"
        bare.parent.mkdir()
        git("init", "-q", "--bare", str(bare))
        seed = t / "seed"
        git("clone", "-q", str(bare), str(seed))
        git("config", "user.email", "t@t", cwd=seed)
        git("config", "user.name", "t", cwd=seed)
        (seed / "f.txt").write_text("x\n")
        git("add", "f.txt", cwd=seed)
        git("commit", "-qm", "seed", cwd=seed)
        git("push", "-q", "origin", "HEAD:refs/heads/9999-x", cwd=seed)

        bon = ws / "envs" / "myrepo-rm9999"
        git("-C", str(bare), "worktree", "add", "-q", str(bon), "9999-x")
        # même branche, autre dossier : exactement « je travaille au mauvais endroit »
        mauvais = ws / "envs" / "myrepo-ailleurs"
        git("-C", str(bare), "worktree", "add", "-q", "--force", str(mauvais), "9999-x")

        md = ws / ".mmi-pm" / "tasks" / "RM9999_x.md"

        def run(cwd):
            env = {k: v for k, v in __import__("os").environ.items()
                   if k != "PM_SKIP_WORKTREE_CHECK"}
            return subprocess.run([sys.executable, str(hook)], cwd=str(cwd),
                                  capture_output=True, text=True, env=env)

        # 1) l'état d'AVANT le correctif : pas de `git.worktree` → garde inerte
        md.write_text(TACHE.format(worktree=""), encoding="utf-8")
        check("sans git.worktree : le mauvais worktree passe (le bug)",
              run(mauvais).returncode, 0)

        # 2) l'état d'APRÈS : le champ est là, la garde mord
        md.write_text(TACHE.format(worktree=f"  worktree: {bon}\n"), encoding="utf-8")
        r = run(mauvais)
        check("avec git.worktree : le mauvais worktree est REFUSÉ", r.returncode, 1)
        check("… le message dit où aller", "myrepo-rm9999" in r.stderr, True)
        check("le bon worktree, lui, passe", run(bon).returncode, 0)

        # 3) l'échappatoire documentée reste ouverte (multi-session légitime)
        import os as _os
        r = subprocess.run([sys.executable, str(hook)], cwd=str(mauvais),
                           capture_output=True, text=True,
                           env=dict(_os.environ, PM_SKIP_WORKTREE_CHECK="1"))
        check("PM_SKIP_WORKTREE_CHECK=1 laisse passer", r.returncode, 0)


if __name__ == "__main__":
    test_unitaire()
    test_vrais_depots()
    test_garde_pre_commit()
    if FAILURES:
        print(f"\n{len(FAILURES)} échec(s) : {', '.join(FAILURES)}")
        sys.exit(1)
    print("\nOK — détection du worktree lié conforme")
