#!/usr/bin/env python3
"""pm-user-enable — rendre l'accès retiré par disable (RM3208). Implémentation : `pm_user_cli.py` ; usage : `mmi-pm user enable --help`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_user_cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(verb="enable"))
