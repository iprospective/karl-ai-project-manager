#!/usr/bin/env python3
"""Test RM3229 — la pause d'une journée HORS période ne s'invite pas dans la proposition.

Les surcharges sont chargées par MOIS entier ; sans bornage, la pause d'une journée
voisine créait une ligne datée d'un autre jour. Combiné au serveur qui rendait la
première journée venue, l'écran affichait alors cette journée-là — ses heures et sa
note (incident du 2026-10-13 : « 08/06 je lis 45 mn proposé… et la note du 04/06 »).

Lancer : python3 scripts/test_pm_timesheet_pauses.py
"""
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("ts_cli", HERE / "pm-timesheet.py")
cli = importlib.util.module_from_spec(spec)
sys.modules["ts_cli"] = cli
spec.loader.exec_module(cli)

ECHECS = []


def verifie(cond, nom):
    print(("  ✓ " if cond else "  ✗ ") + nom)
    if not cond:
        ECHECS.append(nom)


CONF = {"pause": {"client": "iprospective", "project_id": 19, "activity_id": 27,
                  "commentaire": "repas midi", "heures": 1.0}}
SURCHARGES = {
    "2026-06-04": {"client": "calyclay", "pause_h": 0.75},   # hors période
    "2026-06-08": {"client": "calicote", "pause_h": 1.0},    # dans la période
}


def proposition(debut, fin):
    prop = {"lignes": []}
    cli.ajouter_pauses(prop, {"conf": CONF, "surcharges": SURCHARGES, "saisies": [],
                              "debut": debut, "fin": fin})
    return prop["lignes"]


lignes = proposition(datetime(2026, 6, 8), datetime(2026, 6, 10))
verifie([l["jour"] for l in lignes] == ["2026-06-08"],
        "seule la pause de la période proposée (le 04/06 ne s'invite plus)")
verifie(lignes and lignes[0]["minutes"] == 60 and lignes[0]["client"] == "iprospective",
        "…avec sa durée et sa cible")

large = proposition(datetime(2026, 6, 1), datetime(2026, 7, 1))
verifie(sorted(l["jour"] for l in large) == ["2026-06-04", "2026-06-08"],
        "sur le mois entier, les deux pauses sont bien là")

verifie(proposition(datetime(2026, 7, 1), datetime(2026, 8, 1)) == [],
        "un mois sans journée ajustée ne propose aucune pause")

# bornes de pause plutôt que durée : la ligne vaut la différence
SURCHARGES["2026-06-08"] = {"client": "calicote", "pause_debut": "12:30", "pause_fin": "13:15"}
lignes = proposition(datetime(2026, 6, 8), datetime(2026, 6, 10))
verifie(lignes and lignes[0]["minutes"] == 45, "des bornes de pause valent leur durée")

print("\n" + ("ÉCHECS : " + " | ".join(ECHECS) if ECHECS else "Tous les tests passent."))
sys.exit(1 if ECHECS else 0)
