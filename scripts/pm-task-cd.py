#!/usr/bin/env python3
"""pm-task-cd — imprime le chemin de travail d'un ticket (frontmatter `git.worktree`).

Un sous-processus ne peut pas changer le cwd du shell parent : ce script imprime
le chemin (stdout nu, logs sur stderr) et c'est le shell qui s'y place :

    cd "$(pm-task-cd.py <rm_id>)"

Sert à (re)basculer sur le bon worktree sans fouiller le frontmatter à la main
(RM2240 — éviter le travail dans le mauvais worktree). Avec --branch, imprime
la branche attendue (`git.branch`) au lieu du chemin.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--branch", action="store_true",
                    help="Imprime la branche attendue (git.branch) au lieu du chemin")
    args = ap.parse_args()

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"pm-task-cd: RM{args.rm_id} introuvable parmi les projets PM")

    text = md_path.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else None
    git_block = (fm or {}).get("git") or {}

    if args.branch:
        branch = git_block.get("branch")
        if not branch:
            sys.exit(f"pm-task-cd: RM{args.rm_id} : pas de branche au frontmatter "
                     f"(git.branch) — pm-branch-start d'abord")
        print(branch)
        return

    wt = git_block.get("worktree")
    if not wt:
        repo = git_block.get("repo")
        sys.exit(f"pm-task-cd: RM{args.rm_id} : pas de worktree au frontmatter "
                 + (f"(mode in-place dans le repo `{repo}`, branche "
                    f"`{git_block.get('branch')}`)" if repo else
                    "(git.worktree vide — pm-branch-start --worktree d'abord)"))
    wt_path = Path(wt)
    if not wt_path.is_dir():
        sys.exit(f"pm-task-cd: RM{args.rm_id} : worktree enregistré INEXISTANT : {wt}\n"
                 f"  (teardown déjà passé ? autre machine ? — recrée via pm-branch-start --worktree)")
    print(wt_path)


if __name__ == "__main__":
    main()
