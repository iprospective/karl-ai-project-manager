#!/usr/bin/env python3
"""pm-user-add — créer ou compléter le compte PM d'un utilisateur (idempotent) (RM3208). Implémentation : `pm_user_cli.py` ; usage : `mmi-pm user add --help`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_user_cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(verb="add"))
