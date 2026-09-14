#!/usr/bin/env python3
"""pm-index-rebuild — index des projets PM : les liens de co-localisation (RM3033). Voir pm_index.py.
Usage : mmi-pm index-rebuild [--dry-run]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402
import pm_index  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workspaces-root", default=None, help="défaut : $WORKSPACES_ROOT ou /zfs/workspaces")
    a = ap.parse_args()
    cfg = PMConfig.load()
    print(f"reconstruction de l'index sous {cfg.projects_root} (manifeste = meta.yml)")
    r = pm_index.rebuild(cfg.projects_root, a.workspaces_root, a.dry_run)
    print(f"index rebuild : {r['clients']} client(s), {r['projects']} projet(s)" + (" [dry-run]" if a.dry_run else ""))


if __name__ == "__main__":
    main()
