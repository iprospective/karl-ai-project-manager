#!/usr/bin/env python3
"""pm-user-remove — supprimer le compte PM (jamais le compte humain) (RM3208). Implémentation : `pm_user_cli.py` ; usage : `mmi-pm user remove --help`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_user_cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(verb="remove"))
