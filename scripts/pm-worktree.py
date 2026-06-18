#!/usr/bin/env python3
"""pm-worktree — liste / supprime les git worktrees enregistrés par session (RM2034).

Usage :
  pm-worktree.py list [--all]        # worktrees de la session courante (--all : toutes)
  pm-worktree.py remove <path> [--force]   # git worktree remove + purge du registre

Le registre est tenu par pm_session (var/sessions/index.json). « remove » lance
`git worktree remove` puis retire l'entrée du registre de la session courante.
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_session


def cmd_list(args):
    if args.all:
        idx = pm_session.all_records()
        if not idx:
            print("(aucun worktree enregistré)")
            return
        for seq, rec in sorted(idx.items(), key=lambda kv: int(kv[0])):
            wts = rec.get("worktrees", [])
            print("s%s (machine %s) — %d worktree(s)" % (rec.get("seq"), rec.get("machine"), len(wts)))
            for w in wts:
                print("  %s" % w)
    else:
        rec = pm_session.current_record()
        if not rec or not rec.get("worktrees"):
            print("(aucun worktree pour cette session)")
            return
        print("session s%s :" % rec.get("seq"))
        for w in rec["worktrees"]:
            print("  %s" % w)


def cmd_remove(args):
    wt = str(Path(args.path).resolve())
    cmd = ["git", "-C", wt, "worktree", "remove"]
    if args.force:
        cmd.append("--force")
    cmd.append(wt)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ERREUR git worktree remove : %s" % (r.stderr or r.stdout).strip())
    pm_session.forget_worktree(wt)
    print("✓ worktree supprimé + retiré du registre : %s" % wt)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("list", help="Liste les worktrees enregistrés")
    pl.add_argument("--all", action="store_true", help="Toutes les sessions (défaut : session courante)")
    pr = sub.add_parser("remove", help="Supprime un worktree (git + registre)")
    pr.add_argument("path")
    pr.add_argument("--force", action="store_true")
    args = ap.parse_args()
    {"list": cmd_list, "remove": cmd_remove}[args.cmd](args)


if __name__ == "__main__":
    main()
