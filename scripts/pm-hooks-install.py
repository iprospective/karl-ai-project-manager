#!/usr/bin/env python3
"""pm-hooks-install — (ré)installe le hook git post-commit (report conso auto → Redmine,
cf. RM2035) sur les repos PM.

Les git-hooks sont LOCAUX (`.git/hooks/`, non versionnés/clonés) → à (re)poser au
provisioning machine, après tout clone, et à la création d'un workspace PM. Idempotent.

  pm-hooks-install.py                 # tous les repos PM sous /zfs/workspaces + .mmi-pm-core
  pm-hooks-install.py --repo <path>   # un seul repo (appelé par pm-project-new)

Repo PM = dossier contenant un `.mmi-pm` (profondeur 1-2 sous /zfs/workspaces) + le repo
core `.mmi-pm-core` lui-même. Ne clobber JAMAIS un post-commit existant non-symlink.
"""
import argparse
import subprocess
import sys
from pathlib import Path

WORKSPACES = Path("/zfs/workspaces")
PM_CORE = WORKSPACES / ".mmi-pm-core"
HOOK_SRC = PM_CORE / "scripts" / "pm-post-commit.py"
# pre-push anti-id-prédit (RM2224) : posé sur le repo racine ET les bares repos/*.git
# (les branches de ticket partent des worktrees envs/, dont les hooks vivent au bare).
PREPUSH_SRC = PM_CORE / "scripts" / "pm-pre-push"


def git_dir(repo):
    try:
        return Path(subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--absolute-git-dir"],
            text=True, stderr=subprocess.DEVNULL).strip())
    except Exception:
        return None


def install_one(repo, seen):
    gd = git_dir(repo)
    if gd is None:
        return ("skip", f"{repo} : pas un repo git")
    if str(gd) in seen:
        return None                      # repo déjà traité (workspaces partageant un .git)
    seen.add(str(gd))
    results = []
    for name, src in (("post-commit", HOOK_SRC), ("pre-push", PREPUSH_SRC)):
        hook = gd / "hooks" / name
        hook.parent.mkdir(parents=True, exist_ok=True)
        if hook.exists() and not hook.is_symlink():
            results.append(("warn", f"{repo} : {name} existant (non-symlink) → fusion manuelle"))
            continue
        try:
            if hook.is_symlink() and hook.resolve() == src.resolve():
                results.append(("ok", f"{repo} : {name} déjà installé"))
                continue
        except OSError:
            pass
        try:
            if hook.is_symlink() or hook.exists():
                hook.unlink()
            hook.symlink_to(src)
        except OSError as e:
            # repo privsep (ex. .mmi-pm-core : .git root-owned) → à poser par la
            # couche privilégiée (mmi-pm core update), pas bloquant ici.
            results.append(("warn", f"{repo} : {name} non posé ({e.strerror}) — couche privilégiée requise"))
            continue
        results.append(("new", f"{repo} : {name} installé"))
    worst = {"warn": 0, "new": 1, "ok": 2}
    results.sort(key=lambda r: worst[r[0]])
    return results[0] if len(results) == 1 else (results[0][0], " ; ".join(r[1] for r in results))


def discover():
    """Repos PM : dossiers parents d'un .mmi-pm (prof. 1-2) + .mmi-pm-core."""
    repos = set()
    for pat in ("*/.mmi-pm", "*/*/.mmi-pm"):
        for p in WORKSPACES.glob(pat):
            repos.add(p.parent)
            # bares du layout RM1993 : hooks partagés par tous les worktrees envs/
            for bare in (p.parent / "repos").glob("*.git"):
                repos.add(bare)
    repos.add(PM_CORE)
    return sorted(repos)


def main():
    ap = argparse.ArgumentParser(
        description="(Ré)installe le hook git post-commit (report conso) sur les repos PM")
    ap.add_argument("--repo", help="un seul repo (sinon : tous les repos PM)")
    args = ap.parse_args()
    if not HOOK_SRC.exists():
        sys.exit(f"ERREUR : script hook introuvable : {HOOK_SRC}")

    repos = [Path(args.repo)] if args.repo else discover()
    seen = set()
    counts = {"new": 0, "ok": 0, "warn": 0, "skip": 0}
    for r in repos:
        res = install_one(r, seen)
        if res is None:
            continue
        kind, msg = res
        counts[kind] += 1
        icon = {"new": "✓", "ok": "·", "warn": "⚠", "skip": "—"}[kind]
        print(f"  {icon} {msg}")
    print(f"\n-- {counts['new']} installé(s), {counts['ok']} déjà OK, "
          f"{counts['warn']} à fusionner manuellement, {counts['skip']} ignoré(s) --")


if __name__ == "__main__":
    main()
