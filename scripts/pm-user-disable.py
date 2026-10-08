#!/usr/bin/env python3
"""pm-user-disable — retirer l'accès PM d'un utilisateur (réversible) (RM3208). Implémentation : `pm_user_cli.py` ; usage : `mmi-pm user disable --help`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_user_cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(verb="disable"))
