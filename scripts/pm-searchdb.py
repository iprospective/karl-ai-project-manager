#!/usr/bin/env python3
"""pm-searchdb — l'index de requêtage de karl-PM (RM3128).

Une PROJECTION du Markdown, qui reste la source de vérité : rien ne naît ici, et
`rebuild` reconstruit tout depuis les fiches. Voir `pm_searchdb` pour le pourquoi.

⚠ `mmi-pm index-*` est un AUTRE domaine (l'index des symlinks de projets, RM3033).

    mmi-pm searchdb status                 volume, fraîcheur, divergence
    mmi-pm searchdb update                 incrémental — le régime NORMAL
    mmi-pm searchdb rebuild                reconstruction complète (secours, initialisation)
    mmi-pm searchdb query --text "…"       recherche FTS5 (BM25)
    mmi-pm searchdb count                  compteur par statut (ce que rafraîchit le cockpit)

`update` ne retouche que les fiches dont l'empreinte a bougé et retire les disparues :
c'est ce qui tient à l'échelle, là où un rescan complet ne ferait que déplacer le coût.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_searchdb as db
from pm_output import out
from pm_paths import PMConfig


def _print(data, as_json):
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="Index de requêtage PM (projection du Markdown).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for verbe in ("status", "update", "rebuild", "count"):
        p = sub.add_parser(verbe)
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("query")
    p.add_argument("--text")
    p.add_argument("--status", dest="status_")
    p.add_argument("--project")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = PMConfig.load()
    con = db.connect(cfg)
    try:
        if args.cmd == "rebuild":
            r = db.rebuild(cfg, con)
            if _print(r, args.json):
                out.op("searchdb rebuild", extra=f"{r['indexed']} fiche(s) en {r['seconds']} s"
                       + (f", {r['skipped']} ignorée(s)" if r["skipped"] else ""))
        elif args.cmd == "update":
            r = db.update(cfg, con)
            if _print(r, args.json):
                out.op("searchdb update", extra=f"{r['updated']} à jour, {r['removed']} retirée(s), "
                       f"{r['unchanged']} inchangée(s) en {r['seconds']} s")
        elif args.cmd == "count":
            c = db.count_by_status(cfg, con)
            if _print(c, args.json):
                for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
                    print(f"  {v:>5}  {k}")
        elif args.cmd == "status":
            s = db.status(cfg, con)
            if _print(s, args.json):
                print(f"index : {s['tickets']} ticket(s) — {s['db']}")
                print(f"  disque : {s['on_disk']} fiche(s)")
                print(f"  dernier rebuild : {s['last_rebuild'] or '—'}")
                print(f"  dernière maj    : {s['last_update'] or '—'}")
                if s["stale"] or s["orphans"]:
                    out.warn(f"index EN RETARD : {s['stale']} fiche(s) modifiée(s), "
                             f"{s['orphans']} disparue(s) — `mmi-pm index update`")
                else:
                    print("  ✓ à jour")
        elif args.cmd == "query":
            r = db.query(cfg, text=args.text, status_=args.status_,
                               project=args.project, limit=args.limit, con=con)
            if _print(r, args.json):
                if not r:
                    print("aucun résultat")
                for t in r:
                    print(f"RM{t['rm_id']} [{t['status']}] {t['entity']}/{t['project']} — {t['title']}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
