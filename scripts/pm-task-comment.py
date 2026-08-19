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
from pm_output import out
import pm_git
import pm_scope


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--note", required=True, help="Note (ou '-' pour stdin)")
    ap.add_argument("--private", action="store_true", help="Note privée Redmine")
    ap.add_argument("--no-log", action="store_true", help="Ne pas appender au .log.md")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git (RM1834)")
    ap.add_argument("--cross-project", action="store_true", help="Autorise consciemment une écriture sur un ticket d'un AUTRE projet (garde RM2274).")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    note = sys.stdin.read() if args.note == "-" else args.note
    note = note.strip()
    if not note:
        sys.exit("ERREUR : note vide")

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    pm_scope.assert_task_scope(args.rm_id, md_path, args.cross_project, "pm-task-comment")
    if not md_path and not args.no_log:
        out.warn(f"aucun fichier RM{args.rm_id}_*.md (log skip), poste quand même la note Redmine")

    # Pré-flight: la note doit être passée à redmine-post-note.py via stdin si '-', sinon en arg
    cmd = [sys.executable, str(Path(__file__).parent / "redmine-post-note.py"),
           "--issue", str(args.rm_id), "--note", note]
    if args.private:
        cmd.append("--private")
    # Identité par utilisateur (T1/RM2497) : on ne force PLUS karl. La clé perso du
    # dev (REDMINE_API_KEY, ~/.config/mmi-pm/.env) est déjà dans l'environnement via
    # PMConfig ; redmine-post-note.py la préfère (fallback karl). L'action est ainsi
    # attribuée au bon compte. Le sous-process hérite de os.environ tel quel.
    r = subprocess.run(cmd, check=False, capture_output=True, text=True)
    out.info((r.stdout or "").rstrip())
    if r.returncode != 0:
        out.fail(f"ERREUR redmine-post-note (exit {r.returncode}) :\n"
                 f"{(r.stderr or r.stdout or '').rstrip()}")
    # ligne dense unique (contrat T1, CDC RM2316) — détail en --verbose / log / Redmine
    out.op("comment", rm=args.rm_id)

    if md_path and not args.no_log:
        log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
        entry = f"\n## {ts} — Note postée\nTokens : 0 | Durée : 0 min\n\n{note}\n"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(entry)
        out.info(f"✓ Log local appendé : {log_path.relative_to(cfg.projects_root)}")
        if not args.no_commit:
            pm_git.autocommit([log_path], f"pm(comment): RM{args.rm_id} note Redmine + log")


if __name__ == "__main__":
    main()
