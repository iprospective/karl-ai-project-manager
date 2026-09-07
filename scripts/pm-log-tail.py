#!/usr/bin/env python3
"""pm-log-tail — lit le journal structuré (RM3010) : `mmi-pm log-tail [--category auth,api] [--level warn] [--since ISO] [--limit N] [-q texte] [-f]`.

Sortie lisible (une ligne par enregistrement, champs en clair) ou JSON Lines (`--json`). `-f` suit le fichier (nouveaux enregistrements
toutes les 2 s). Le journal vit dans `logs/karl-agent.jsonl` (ou KARL_JOURNAL_DIR) ; voir `scripts/pm_log.py`.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_log import tail, stats, LEVELS, CATEGORIES  # noqa: E402

COLORS = {"debug": "\033[90m", "info": "\033[0m", "warn": "\033[33m", "error": "\033[31m"}


def fmt(rec: dict, color: bool) -> str:
    extra = " ".join(f"{k}={rec[k]}" for k in rec if k not in ("ts", "level", "cat", "msg"))
    line = f"{rec.get('ts', '')[:19]} {rec.get('level', '?'):5} {rec.get('cat', '?'):8} {rec.get('msg', '')}{(' · ' + extra) if extra else ''}"
    return (COLORS.get(rec.get("level"), "") + line + "\033[0m") if color else line


def main() -> int:
    ap = argparse.ArgumentParser(description="Journal structuré karl-agent / PM (RM3010)")
    ap.add_argument("--category", "-c", help="catégorie(s), csv (" + ", ".join(sorted(CATEGORIES)) + ")")
    ap.add_argument("--level", "-l", default="debug", choices=sorted(LEVELS, key=LEVELS.get), help="sévérité minimale (défaut : debug)")
    ap.add_argument("--since", help="horodatage ISO exclusif")
    ap.add_argument("--limit", "-n", type=int, default=100)
    ap.add_argument("-q", help="texte à chercher (message et champs)")
    ap.add_argument("--json", action="store_true", help="JSON Lines brut")
    ap.add_argument("-f", "--follow", action="store_true", help="suivre le journal")
    ap.add_argument("--stats", action="store_true", help="état du journal (chemin, niveau, compteurs)")
    a = ap.parse_args()
    if a.stats:
        print(json.dumps(stats(), ensure_ascii=False, indent=2)); return 0
    color = sys.stdout.isatty() and not a.json
    since = a.since
    while True:
        recs = tail(a.category, a.level, since, a.limit, a.q)
        for r in recs:
            print(json.dumps(r, ensure_ascii=False) if a.json else fmt(r, color))
        if not a.follow:
            return 0
        if recs:
            since = recs[-1].get("ts", since)
        sys.stdout.flush()
        try:
            time.sleep(2)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
