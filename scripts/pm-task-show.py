#!/usr/bin/env python3
"""pm-task-show — Affiche le détail d'une tâche (MD + tail log + Redmine récent).

Usage :
    pm-task-show.py <RM-id> [--log-lines N] [--fetch-redmine]
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int, help="ID Redmine de la tâche (ex: 1669)")
    ap.add_argument("--log-lines", type=int, default=30, help="Lignes de log à afficher (défaut 30)")
    ap.add_argument("--fetch-redmine", action="store_true", help="Aussi rafraîchir depuis Redmine via redmine-fetch-updates.py")
    args = ap.parse_args()

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : aucun fichier RM{args.rm_id}_*.md trouvé sous {cfg.projects_root}")

    log_path = md_path.with_suffix(".log.md") if md_path.name.endswith(".md") else None
    # find_task already returns the non-log file ; deriver le log
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")

    print(f"━━━ RM{args.rm_id} — {md_path.relative_to(cfg.projects_root)} ━━━\n")
    print(md_path.read_text(encoding="utf-8"))
    print()

    if log_path.is_file():
        print(f"━━━ Dernières entrées du log ({args.log_lines} lignes) ━━━\n")
        lines = log_path.read_text(encoding="utf-8").splitlines()
        for line in lines[-args.log_lines:]:
            print(line)
        print()
    else:
        print(f"(pas de fichier log {log_path.name})\n")

    if args.fetch_redmine:
        print("━━━ Refresh Redmine (via redmine-fetch-updates.py) ━━━\n")
        try:
            subprocess.run(
                [sys.executable, str(Path(__file__).parent / "redmine-fetch-updates.py"),
                 "--issue", str(args.rm_id)],
                check=False,
            )
        except Exception as e:
            print(f"⚠ échec fetch Redmine : {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
