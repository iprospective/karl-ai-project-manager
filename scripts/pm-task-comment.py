#!/usr/bin/env python3
"""pm-task-comment — Poste une note Redmine ET append au log local.

Usage :
    pm-task-comment.py <RM-id> --note "Texte"
    echo "Note multiligne" | pm-task-comment.py <RM-id> --note -
    pm-task-comment.py <RM-id> --note "Privée" --private
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import pm_git


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--note", required=True, help="Note (ou '-' pour stdin)")
    ap.add_argument("--private", action="store_true", help="Note privée Redmine")
    ap.add_argument("--no-log", action="store_true", help="Ne pas appender au .log.md")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git (RM1834)")
    args = ap.parse_args()

    note = sys.stdin.read() if args.note == "-" else args.note
    note = note.strip()
    if not note:
        sys.exit("ERREUR : note vide")

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path and not args.no_log:
        print(f"⚠ aucun fichier RM{args.rm_id}_*.md (log skip), poste quand même la note Redmine", file=sys.stderr)

    # Pré-flight: la note doit être passée à redmine-post-note.py via stdin si '-', sinon en arg
    cmd = [sys.executable, str(Path(__file__).parent / "redmine-post-note.py"),
           "--issue", str(args.rm_id), "--note", note]
    if args.private:
        cmd.append("--private")
    # Use Karl (MAIN) as central account for PM operations
    env = os.environ.copy()
    main = env.get("REDMINE_USER_MAIN_API_KEY")
    if main:
        env["REDMINE_API_KEY"] = main
    r = subprocess.run(cmd, env=env, check=False)
    if r.returncode != 0:
        sys.exit(f"ERREUR redmine-post-note (exit {r.returncode})")

    if md_path and not args.no_log:
        log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
        entry = f"\n## {ts} — Note postée\nTokens : 0 | Durée : 0 min\n\n{note}\n"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(entry)
        print(f"✓ Log local appendé : {log_path.relative_to(cfg.projects_root)}")
        if not args.no_commit:
            pm_git.autocommit([log_path], f"pm(comment): RM{args.rm_id} note Redmine + log")


if __name__ == "__main__":
    main()
