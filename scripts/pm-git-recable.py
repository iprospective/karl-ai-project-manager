#!/usr/bin/env python3
"""pm-git-recable — Recâble en masse les remotes git locaux après un déplacement de groupe GitLab (RM1976).

Quand un groupe GitLab est promu/déplacé (ex. `iprospective/prestashop` →
`prestashop`, `iprospective/dolibarr` → `dolibarr`, `sfy/calicote` → `calicote`),
tous les clones locaux qui pointent vers l'ancien chemin doivent voir leur
remote mis à jour. GitLab pose des redirections, donc rien ne casse, mais on
veut des remotes propres.

Ce script scanne les dépôts git sous --root (défaut /zfs/workspaces, scan borné
et élagué) et, pour chaque remote contenant <ancien>, remplace par <nouveau>.

⚠ Ne touche QUE les remotes locaux. Les remotes côté PROD (serveurs OVH, CI,
hooks) sont hors périmètre — à traiter manuellement avec consentement (cf. ticket).

Usage :
    pm-git-recable.py <ancien-fragment> <nouveau-fragment> [--root DIR] [--dry-run]

Exemples :
    pm-git-recable.py iprospective/prestashop/ prestashop/ --dry-run
    pm-git-recable.py iprospective/dolibarr/ dolibarr/
"""
import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path("/zfs/workspaces")


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def find_git_repos(root):
    """Chemins des dépôts git sous root (find borné, élagué)."""
    r = run(["find", str(root), "-maxdepth", "6",
             "(", "-name", "node_modules", "-o", "-name", "vendor",
             "-o", "-name", ".worktrees", ")", "-prune", "-o",
             "-name", ".git", "-print"])
    return [Path(p).parent for p in r.stdout.splitlines()]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old", help="Fragment de chemin à remplacer (ex. iprospective/prestashop/)")
    ap.add_argument("new", help="Nouveau fragment (ex. prestashop/)")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.old == args.new:
        sys.exit("ERREUR : ancien et nouveau fragments identiques.")

    print(f"== recâblage remotes : '{args.old}' → '{args.new}' (root {args.root}) ==")
    n_repos = n_remotes = 0
    for repo in find_git_repos(Path(args.root)):
        remotes = run(["git", "-C", str(repo), "remote"]).stdout.split()
        for name in remotes:
            url = run(["git", "-C", str(repo), "remote", "get-url", name]).stdout.strip()
            if args.old in url:
                new_url = url.replace(args.old, args.new)
                rel = repo.relative_to(args.root) if str(repo).startswith(args.root) else repo
                if args.dry_run:
                    print(f"  [dry] {rel} [{name}] {url} → {new_url}")
                else:
                    run(["git", "-C", str(repo), "remote", "set-url", name, new_url])
                    print(f"  ✓ {rel} [{name}] → {new_url}")
                n_remotes += 1
        if remotes:
            n_repos += 1
    print(f"== {n_remotes} remote(s) recâblé(s){' (dry-run)' if args.dry_run else ''} "
          f"sur {n_repos} dépôt(s) scanné(s) ==")
    if n_remotes and not args.dry_run:
        print("  ⚠ Rappel : les remotes côté PROD/CI ne sont PAS touchés (hors périmètre).")


if __name__ == "__main__":
    main()
