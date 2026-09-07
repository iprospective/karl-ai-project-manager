#!/usr/bin/env python3
"""pm-index-add — index des projets PM (RM3033, porté de `bin/mmi-pm index add`). Voir pm_index.py.
Usage : mmi-pm index-add <client>/<projet> [chemin-du-workspace] [--dry-run]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402
import pm_index  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("spec", metavar="<client>/<projet>")
    ap.add_argument("path", nargs="?", help="workspace (défaut : $WORKSPACES_ROOT/<client>/<projet>)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = PMConfig.load()
    try:
        r = pm_index.add(cfg.projects_root, a.spec, a.path, a.dry_run)
    except (ValueError, FileNotFoundError) as e:
        sys.exit(f"mmi-pm index-add : {e}")
    print(("[dry] " if a.dry_run else "") + f"index : {r['client']}/{r['project']} -> {r['target']}")


if __name__ == "__main__":
    main()
