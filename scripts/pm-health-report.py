#!/usr/bin/env python3
"""pm-health-report — calcule la santé du système PM et l'écrit (RM3369).

Le cockpit ne joue pas ces contrôles à l'ouverture : ils interrogent l'API
Redmine et balaient le parc de tâches. Il lit le dernier rapport, et en affiche
l'âge — un rapport périmé est lui-même un souci. Ce script est donc ce qui doit
tourner en tâche de fond (timer, cron), ou à la main après une réparation.

Usage :
    pm-health-report.py                    # calcule, écrit var/pm-health.json
    pm-health-report.py --print            # + affiche le rapport lisible
    pm-health-report.py --only "Normes"    # une famille (répétable)
    pm-health-report.py --check            # n'écrit rien : affiche et sort 1 si majeur
    pm-health-report.py --json             # le rapport sur la sortie standard

Sortie : 0 si aucun souci MAJEUR (aucune ligne `error` dans les familles
surveillées), 1 sinon — utilisable tel quel dans un timer qui alerte.
"""
import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import pm_health as H          # noqa: E402

MARK = {"ok": "✓", "info": "·", "warn": "⚠", "error": "✗"}


def render(report):
    """Le rapport en texte, familles en tête, lignes en défaut d'abord."""
    lines = []
    summary = report.get("summary") or {}
    counts = summary.get("counts") or {}
    alerts = report.get("alerts") or {}
    lines.append(f"== santé PM — {report.get('generated_label') or '?'} "
                 f"— {alerts.get('major', 0)} souci(s) majeur(s) ==")
    for g in report.get("groups") or []:
        checks = g.get("checks") or []
        bad = [c for c in checks if c.get("level") in ("warn", "error")]
        lines.append(f"-- {g.get('name')} ({len(bad)}/{len(checks)} en défaut)")
        for c in sorted(checks, key=lambda c: -H.LEVEL_RANK.get(c.get("level"), 0)):
            if c.get("level") == "ok" and bad:
                continue                      # le détail vert n'intéresse que si tout va bien
            lines.append(f"  {MARK.get(c.get('level'), '·')} {c.get('label')}"
                         + (f" : {c.get('detail')}" if c.get("detail") else ""))
            if c.get("fix") and c.get("level") in ("warn", "error"):
                lines.append(f"      → {c['fix']}")
    lines.append(f"== {counts.get('error', 0)} erreur(s), {counts.get('warn', 0)} "
                 f"avertissement(s) ==")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", action="append", metavar="FAMILLE",
                    help="ne joue que cette famille (répétable) : "
                         + ", ".join(n for n, _ in H.FAMILIES))
    ap.add_argument("--out", help="chemin du rapport (défaut : var/pm-health.json)")
    ap.add_argument("--check", action="store_true",
                    help="n'écrit pas le rapport : contrôle seulement")
    ap.add_argument("--print", dest="show", action="store_true", help="affiche le rapport")
    ap.add_argument("--json", action="store_true", help="rapport JSON sur stdout")
    args = ap.parse_args()

    known = {n for n, _ in H.FAMILIES}
    only = None
    if args.only:
        only = set(args.only)
        inconnues = only - known
        if inconnues:
            sys.exit("famille inconnue : " + ", ".join(sorted(inconnues))
                     + " — connues : " + ", ".join(sorted(known)))

    report = H.build_report(only=only)
    if not args.check:
        path = H.write_report(report, args.out)
        if not args.json:
            print(f"✓ rapport écrit : {path}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    elif args.show or args.check:
        print(render(report))

    major = (report.get("alerts") or {}).get("major", 0)
    if not args.json and not args.show and not args.check:
        print(f"  {major} souci(s) majeur(s), "
              f"{(report.get('alerts') or {}).get('count', 0)} ligne(s) en défaut")
    return 1 if major else 0


if __name__ == "__main__":
    sys.exit(main())
