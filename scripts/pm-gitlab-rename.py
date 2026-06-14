#!/usr/bin/env python3
"""pm-gitlab-rename — Renomme/déplace un repo GitLab + recâble les remotes locaux (RM1976).

Facilite la réconciliation des noms (convention RM1976) : renommer un projet
GitLab (slug et/ou nom affiché), éventuellement le transférer dans un autre
groupe, et mettre à jour automatiquement les remotes git des clones locaux qui
le référencent (sous /zfs/workspaces).

Usage :
    pm-gitlab-rename.py <projet> [--to-path NEW] [--to-name "Nom"] [--to-group GRP]
                        [--no-remotes] [--dry-run]

  <projet>      : `groupe/chemin` ou id numérique du projet GitLab.
  --to-path     : nouveau slug (path) du repo (l'URL change ; GitLab pose une redirection).
  --to-name     : nouveau nom affiché (défaut : dérivé de --to-path si absent).
  --to-group    : transférer le repo dans un autre groupe (chemin ou id).
  --no-remotes  : ne PAS recâbler les remotes locaux (par défaut, on les recâble).
  --dry-run     : montre tout sans rien modifier.

Au moins une de --to-path / --to-name / --to-group est requise.

Non destructif côté contenu (rename = métadonnée + redirection). Idempotent-friendly.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

GITLAB_HOST = "gitlab.iprospective.fr"
WS_ROOT = Path("/zfs/workspaces")
_LAST_ERROR = None


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def glab(path, method="GET", fields=None):
    global _LAST_ERROR
    cmd = ["glab", "api", "--hostname", GITLAB_HOST, "--method", method, path]
    for k, v in (fields or {}).items():
        cmd += ["-f", f"{k}={v}"]
    r = run(cmd)
    data = None
    try:
        data = json.loads(r.stdout) if r.stdout.strip() else None
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and ("message" in data or "error" in data) and "id" not in data:
        _LAST_ERROR = str(data.get("message") or data.get("error"))
        return None
    if r.returncode != 0:
        _LAST_ERROR = (r.stderr or r.stdout).strip()[:200] or f"exit {r.returncode}"
        return None
    return data


def resolve_project(ref):
    """ref = 'group/path' ou id → dict projet GitLab (ou None).

    Résolution par RECHERCHE dans le groupe (le GET par path encodé `%2F` est
    non fiable côté instance — 404 ; gotcha NORMS)."""
    if ref.isdigit():
        return glab(f"projects/{ref}")
    group_ref, _, repo_path = ref.rpartition("/")
    gid = group_id(group_ref)
    if gid is None:
        return None
    for p in (glab(f"groups/{gid}/projects?search={repo_path}&include_subgroups=true&per_page=100") or []):
        if p.get("path") == repo_path:
            return p
    return None


def group_id(group_ref):
    if group_ref.isdigit():
        g = glab(f"groups/{group_ref}")
        return g["id"] if g else None
    for g in (glab(f"groups?search={group_ref.split('/')[-1]}") or []):
        if g.get("full_path") == group_ref:
            return g["id"]
    return None


def find_local_remotes(old_pwn):
    """[(repo_dir, remote_name, old_url)] des clones locaux référençant old_pwn.

    Scan borné/élagué (find -maxdepth, prune node_modules/vendor/.worktrees) —
    rglob sur tout /zfs/workspaces est trop lent."""
    find = run(["find", str(WS_ROOT), "-maxdepth", "6",
                "(", "-name", "node_modules", "-o", "-name", "vendor",
                "-o", "-name", ".worktrees", ")", "-prune", "-o",
                "-name", ".git", "-print"])
    hits = []
    for gitpath in find.stdout.splitlines():
        repo = Path(gitpath).parent
        r = run(["git", "-C", str(repo), "remote", "-v"])
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and old_pwn in parts[1] and "(fetch)" in line:
                hits.append((repo, parts[0], parts[1]))
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--to-path")
    ap.add_argument("--to-name")
    ap.add_argument("--to-group")
    ap.add_argument("--no-remotes", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (args.to_path or args.to_name or args.to_group):
        sys.exit("ERREUR : préciser au moins --to-path, --to-name ou --to-group.")

    proj = resolve_project(args.project)
    if not proj:
        sys.exit(f"ERREUR : projet '{args.project}' introuvable ({_LAST_ERROR})")
    pid = proj["id"]
    old_pwn = proj["path_with_namespace"]
    ns_path = old_pwn.rsplit("/", 1)[0]
    print(f"== {old_pwn} (id {pid}) ==")

    # nouvelle path_with_namespace prévue (pour recâbler les remotes)
    new_ns = args.to_group or ns_path
    new_path = args.to_path or proj["path"]
    new_pwn = f"{new_ns}/{new_path}"

    # 1. Transfert de groupe (si demandé)
    if args.to_group:
        gid = group_id(args.to_group)
        if gid is None:
            sys.exit(f"ERREUR : groupe cible '{args.to_group}' introuvable ({_LAST_ERROR})")
        if args.dry_run:
            print(f"  [dry] transfert → groupe {args.to_group} (id {gid})")
        else:
            # GitLab : le transfert de projet est un PUT (POST → 404 sur l'instance)
            r = glab(f"projects/{pid}/transfer", "PUT", {"namespace": str(gid)})
            print(f"  ✓ transféré → {args.to_group}" if r else
                  f"  ✗ transfert échoué : {_LAST_ERROR}")
            if not r:
                sys.exit(1)

    # 2. Rename path / name
    fields = {}
    if args.to_path:
        fields["path"] = args.to_path
    if args.to_name:
        fields["name"] = args.to_name
    elif args.to_path:
        fields["name"] = args.to_path  # nom affiché = slug si non précisé
    if fields:
        if args.dry_run:
            print(f"  [dry] PUT projet : {fields}")
        else:
            r = glab(f"projects/{pid}", "PUT", fields)
            if not r:
                sys.exit(f"  ✗ renommage échoué : {_LAST_ERROR}")
            new_pwn = r["path_with_namespace"]
            print(f"  ✓ renommé : {old_pwn} → {new_pwn}")

    # 3. Recâblage des remotes locaux
    if not args.no_remotes:
        hits = find_local_remotes(old_pwn)
        if not hits:
            print("  · aucun remote local à recâbler")
        for repo, name, url in hits:
            new_url = url.replace(old_pwn, new_pwn)
            if args.dry_run:
                print(f"  [dry] {repo.relative_to(WS_ROOT)} [{name}] {url} → {new_url}")
            else:
                run(["git", "-C", str(repo), "remote", "set-url", name, new_url])
                print(f"  ✓ remote {repo.relative_to(WS_ROOT)} [{name}] → {new_url}")

    print("== terminé ==" + (" (DRY-RUN)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
