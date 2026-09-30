#!/usr/bin/env python3
"""Tests RM3177 — la veille du budget de précharge : paliers, tendance, historique.

Ce que ces tests protègent :
  * **des paliers, pas un seul seuil** : on doit être prévenu AVANT d'avoir entamé la marge ;
  * **la tendance** dit ce qu'il faut faire, la valeur seule ne distingue pas un plateau d'une
    dérive ;
  * **le message reste STABLE**, la tendance part en champ — sinon chaque jour écrirait une
    entrée neuve et l'anti-répétition du fil tomberait ;
  * **une mesure par jour** : plusieurs passages le même jour n'aplatissent pas la pente.

Lancer : python3 scripts/test_pm_context_budget_tendance.py
"""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("cb", HERE / "pm-context-budget.py")
CB = importlib.util.module_from_spec(spec); spec.loader.exec_module(CB)

# — paliers —
check("sous 80 % : rien", CB.palier(0.79) is None)
check("80 % : info (prévenir AVANT la marge)", CB.palier(0.80)[0] == "info")
check("90 % : warn", CB.palier(0.90)[0] == "warn")
check("100 % : critical", CB.palier(1.00)[0] == "critical")
check("--warn-ratio honoré : warn à 0,85, info cale en dessous",
      CB.palier(0.86, warn=0.85)[0] == "warn" and CB.palier(0.76, warn=0.85)[0] == "info")
check("le plafond (1.0) reste fixe quel que soit warn", CB.palier(1.0, warn=0.95)[0] == "critical")
msgs = {CB.palier(f)[1] for f in (0.8, 0.85, 0.89)}
check("un même palier garde UN message, quelle que soit la valeur (dédup du fil)", len(msgs) == 1)

# — tendance —
M = lambda d, p: {"date": d, "pct": p}
now = datetime(2026, 9, 21)
d, j = CB.tendance([M("2026-09-01", 91.4), M("2026-09-10", 94.0), M("2026-09-21", 96.7)], now)
check("la dérive est mesurée : +5,3 pts", d == 5.3)
check("… sur les jours réellement couverts", j == 20)
check("une seule mesure : pas de tendance", CB.tendance([M("2026-09-21", 96.0)], now) == (None, 0))
check("aucune mesure : pas de tendance", CB.tendance([], now) == (None, 0))
check("hors fenêtre : ignoré",
      CB.tendance([M("2026-07-01", 50.0), M("2026-09-21", 96.0)], now) == (None, 0))
check("un plateau rend 0, pas « rien »",
      CB.tendance([M("2026-09-10", 96.0), M("2026-09-21", 96.0)], now)[0] == 0.0)
check("une baisse est dite négative",
      CB.tendance([M("2026-09-10", 98.0), M("2026-09-21", 95.0)], now)[0] == -3.0)
check("moins de 2 jours d'écart : pas une tendance",
      CB.tendance([M("2026-09-20", 95.0), M("2026-09-21", 96.0)], now) == (None, 0))
check("des lignes corrompues n'arrêtent pas le calcul",
      CB.tendance([{"x": 1}, M("bidon", 3), M("2026-09-10", 90.0), M("2026-09-21", 95.0)], now)[0] == 5.0)

# — historique : une mesure par jour, la dernière gagne —
with tempfile.TemporaryDirectory() as tmp:
    os.environ["PM_NOTIFY_DIR"] = tmp
    CB._enregistre("worker-dev", 29000, 30000, 96.0)
    lignes = CB._enregistre("worker-dev", 29100, 30000, 97.0)
    check("deux passages le même jour → UNE ligne", len(lignes) == 1)
    check("… et c'est la dernière mesure qui gagne", lignes[0]["pct"] == 97.0)
    f = pathlib.Path(tmp) / "norms-budget-history.jsonl"
    check("l'historique vit dans le state du fil (donc isolé en test)", f.exists())

# — le message ne porte JAMAIS la tendance —
src = (HERE / "pm-context-budget.py").read_text(encoding="utf-8")
check("la tendance part en champ", "tendance=delta" in src)
check("la mesure est enregistrée même quand la marge est saine (une tendance tardive ne sert à rien)",
      src.index("_enregistre(") < src.index("marge saine"))

print(("ÉCHEC : " + "; ".join(fails)) if fails else "OK — veille du budget de précharge")
sys.exit(1 if fails else 0)
