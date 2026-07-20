#!/usr/bin/env python3
"""pm-task-log — lecture CIBLÉE du journal d'un ticket (RM2363, CDC RM2316 § S2).

Remplace les `cat`/`tail` manuels du `.log.md` (mesurés : 706 manipulations,
214 k tokens injectés — audit RM2275). Par défaut : les N dernières entrées en
mode résumé (en-tête + 1re ligne du corps). `--full` restitue les entrées
sélectionnées en entier ; `--grep` filtre sur le contenu.

Usage :
    pm-task-log.py <RM-id>                    # 5 dernières entrées, résumées
    pm-task-log.py <RM-id> --tail 10 --full   # 10 dernières, complètes
    pm-task-log.py <RM-id> --grep 'MR !\\d+'   # entrées qui matchent (résumées)
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from pm_output import out

LOG_HDR_RE = re.compile(r"^## \S+ — .+$")


def parse_entries(text):
    """Découpe le .log.md en entrées : liste de (header, [lignes de corps])."""
    entries = []
    cur = None
    for line in text.splitlines():
        if LOG_HDR_RE.match(line):
            cur = (line, [])
            entries.append(cur)
        elif cur is not None:
            cur[1].append(line)
    return entries


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--tail", type=int, default=5, metavar="N",
                    help="N dernières entrées (défaut 5 ; 0 = toutes)")
    ap.add_argument("--grep", metavar="REGEX",
                    help="Ne garde que les entrées dont le contenu matche (re.search, i)")
    ap.add_argument("--full", action="store_true",
                    help="Entrées complètes (défaut : en-tête + 1re ligne)")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    cfg = PMConfig.load()
    md = cfg.find_task(args.rm_id)
    if not md:
        out.fail(f"fichier RM{args.rm_id}_*.md introuvable")
    log = md.parent / md.name.replace(".md", ".log.md")
    if not log.is_file():
        out.fail(f"pas de journal : {log.name}")

    entries = parse_entries(log.read_text(encoding="utf-8"))
    total = len(entries)
    if args.grep:
        rx = re.compile(args.grep, re.I)
        entries = [e for e in entries if rx.search(e[0]) or rx.search("\n".join(e[1]))]
    if args.tail:
        entries = entries[-args.tail:]

    for hdr, body in entries:
        if args.full:
            print(hdr)
            print("\n".join(body).rstrip() + "\n")
        else:
            first = next((l.strip() for l in body
                          if l.strip() and not l.strip().startswith("Tokens :")), "")
            print(f"{hdr[3:]}"[:120])
            if first:
                print(f"  · {first[:110]}")
    shown = len(entries)
    if shown < total:
        print(f"… ({shown}/{total} entrées — --tail 0 pour tout, --full pour le détail)")


if __name__ == "__main__":
    main()
