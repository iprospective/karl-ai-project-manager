#!/usr/bin/env python3
"""pm-index-list — index des projets PM (RM3033, porté de `bin/mmi-pm index list`). Voir pm_index.py.
Usage : mmi-pm index-list """
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402
import pm_index  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.parse_args()
    cfg = PMConfig.load()
    try:
        print(pm_index.format_listing(pm_index.listing(cfg.projects_root)))
    except FileNotFoundError as e:
        sys.exit(f"mmi-pm index-list : {e}")


if __name__ == "__main__":
    main()
