#!/usr/bin/env python3
"""pm-projects-index-remove — index des projets PM : les liens de co-localisation (RM3033 ; renomme par RM3142). Voir pm_projects_index.py.
Usage : mmi-pm projects-index-remove <client>/<projet> [--dry-run]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402
import pm_projects_index as pm_index  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("spec", metavar="<client>/<projet>")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = PMConfig.load()
    try:
        r = pm_index.remove(cfg.projects_root, a.spec, a.dry_run)
    except (ValueError, FileNotFoundError) as e:
        sys.exit(f"mmi-pm projects-index-remove : {e}")
    print(("[dry] " if a.dry_run else "") + f"index : retiré {r['client']}/{r['project']}")


if __name__ == "__main__":
    main()
