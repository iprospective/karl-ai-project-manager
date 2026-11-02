#!/usr/bin/env python3
"""pm-knowledge — lire la knowledge PM en local, snapshot ou remote (RM3609)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_knowledge import KnowledgeError, KnowledgeStore, MODES  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pm-knowledge", description=__doc__)
    parser.add_argument("--mode", choices=MODES, help="local (defaut), snapshot ou remote")
    parser.add_argument("--local", help="racine knowledge PM (defaut : <core>/knowledge)")
    parser.add_argument("--snapshot", help="bundle KB local")
    parser.add_argument("--url", help="base URL KB")
    sub = parser.add_subparsers(dest="command", required=True)

    get = sub.add_parser("get", help="lire une fiche par id")
    get.add_argument("id")
    get.add_argument("--no-body", action="store_true")

    search = sub.add_parser("search", help="rechercher dans la knowledge")
    search.add_argument("query")

    view = sub.add_parser("view", help="lire une vue")
    view.add_argument("name")
    view.add_argument("--tool")
    view.add_argument("--version")
    view.add_argument("--component")
    view.add_argument("--php")

    sub.add_parser("info", help="afficher le mode et les chemins resolus")
    args = parser.parse_args(argv)

    try:
        store = KnowledgeStore(mode=args.mode, local=args.local, snapshot=args.snapshot, url=args.url)
        if args.command == "info":
            print(json.dumps(store.info(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "get":
            doc = store.get(args.id, body=not args.no_body)
            if doc is None:
                print(f"introuvable : {args.id}", file=sys.stderr)
                return 1
            print(json.dumps(doc, ensure_ascii=False, indent=2, default=str))
            return 0
        if args.command == "search":
            rows = store.search(args.query)
            for row in rows:
                print(f"{row.get('id')}\t{row.get('title', '')}")
            return 0 if rows else 1
        if args.command == "view":
            filters = {key: getattr(args, key) for key in ("tool", "version", "component", "php") if getattr(args, key)}
            print(json.dumps(store.view(args.name, filters), ensure_ascii=False, indent=2, default=str))
            return 0
    except KnowledgeError as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
