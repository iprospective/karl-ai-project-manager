#!/usr/bin/env python3
"""Tests RM2716 — traitement en série d'un lot de tickets du worklog.

Ce qu'on protège (les gardes valent plus que la fonctionnalité) :
  - aucun ticket non actionnable n'entre dans la consigne, et chaque exclusion
    porte sa RAISON (rien d'écarté en silence) ;
  - un statut inconnu est écarté, jamais deviné ;
  - le plafond de 10 tient, et ne se contourne qu'explicitement ;
  - `dry_run` ne touche à aucune session (c'est le récapitulatif d'avant envoi) ;
  - la consigne exige les trois retours arbitrés (statut NORMS, notification de
    fin, récapitulatif au worklog).

Lancer : python3 scripts/test_karl_agent_batch.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def raises(code, fn):
    try:
        fn()
        return False
    except ka.ApiError as e:
        return e.code == code


# — batch_plan : ce qui part, ce qui est écarté, et pourquoi —
ITEMS = [
    {"rm_id": "10", "status": "a_faire", "title": "dev"},
    {"rm_id": "RM11", "status": "a_etudier_chiffrer", "title": "étude"},
    {"rm_id": "12", "status": "a_tester_demandeur", "title": "chez le demandeur"},
    {"rm_id": "13", "status": "ferme"},
    {"rm_id": "14", "status": "statut_invente"},
    {"rm_id": "10", "status": "a_faire"},          # doublon
    {"rm_id": "pas-un-id", "status": "a_faire"},   # id invalide
]
plan = ka.batch_plan(ITEMS)
check("les actionnables partent", [t["rm_id"] for t in plan["todo"]] == ["10", "11"],
      str([t["rm_id"] for t in plan["todo"]]))
check("préfixe RM toléré", any(t["rm_id"] == "11" for t in plan["todo"]))
check("doublon ignoré", len(plan["todo"]) == 2)
check("id invalide ignoré", all(t["rm_id"].isdigit() for t in plan["todo"]))
check("a_faire → traiter", plan["todo"][0]["action"] == "traiter")
check("a_etudier_chiffrer → étudier", plan["todo"][1]["action"] == "etudier")
skipped = {s["rm_id"]: s for s in plan["skipped"]}
check("un ticket chez le demandeur est ÉCARTÉ", "12" in skipped)
check("…avec une raison lisible", "verdict" in skipped["12"]["reason"], skipped["12"]["reason"])
check("un ticket fermé est écarté", "13" in skipped)
check("un statut INCONNU est écarté, pas deviné",
      "14" in skipped and "aucune action définie" in skipped["14"]["reason"])
check("liste vide tolérée", ka.batch_plan([])["todo"] == [] and ka.batch_plan(None)["todo"] == [])

# — batch_prompt : consigne auto-portante, exigences de retour —
p = ka.batch_prompt(plan["todo"])
check("la consigne numérote les tickets dans l'ordre", "1. RM10" in p and "2. RM11" in p)
check("elle porte l'action de chaque ticket",
      "livrer" in p and "soumettre l'étude à validation" in p)
check("elle impose la SÉRIE (un ticket à la fois)", "un ticket à la fois" in p)
check("elle exige le statut de retour NORMS",
      "etude_chiffrage_a_valider" in p and "a_tester_demandeur" in p)
check("elle exige la notification de fin de lot", "notify" in p and "lot terminé" in p)
check("elle exige le récapitulatif au worklog", "pm-session-status" in p)
check("elle interdit de forcer un ticket bloqué", "NE FORCE PAS" in p)
check("consigne vide tolérée", isinstance(ka.batch_prompt([]), str))

# — op_worklog_batch : gardes —
sent = []
ka.op_send = lambda payload: sent.append(payload) or {"sent": True}
ka._has_session = lambda sid: True

check("session invalide → 400", raises(400, lambda: ka.op_worklog_batch({"rm_id": "../x", "items": ITEMS})))
check("items vide → 400", raises(400, lambda: ka.op_worklog_batch({"rm_id": "70", "items": []})))
check("aucun actionnable → 400 (on n'envoie pas un lot vide)",
      raises(400, lambda: ka.op_worklog_batch({"rm_id": "70", "items": [{"rm_id": "1", "status": "ferme"}]})))

dry = ka.op_worklog_batch({"rm_id": "70", "items": ITEMS, "dry_run": True})
check("dry_run n'envoie RIEN", dry["sent"] is False and not sent)
check("dry_run rend le récapitulatif complet",
      dry["count"] == 2 and len(dry["skipped"]) == 3 and dry["prompt"])

res = ka.op_worklog_batch({"rm_id": "70", "items": ITEMS})
check("l'envoi part dans la session ATTACHÉE (aucune session créée)",
      res["sent"] is True and len(sent) == 1 and sent[0]["rm_id"] == "70")
check("le message envoyé EST la consigne composée", sent[0]["msg"] == res["prompt"])

# plafond
gros = [{"rm_id": str(100 + i), "status": "a_faire"} for i in range(12)]
check("au-delà de 10 tickets → 409", raises(409, lambda: ka.op_worklog_batch({"rm_id": "70", "items": gros})))
big = ka.op_worklog_batch({"rm_id": "70", "items": gros, "allow_large": True})
check("…contournable seulement explicitement", big["count"] == 12)
check("le plafond ne compte QUE les actionnables",
      ka.op_worklog_batch({"rm_id": "70", "items": gros[:10] + [{"rm_id": "999", "status": "ferme"}]})["count"] == 10)

# session absente : on ne prétend pas avoir envoyé
ka._has_session = lambda sid: False
check("session éteinte → 404 (et rien d'envoyé)",
      raises(404, lambda: ka.op_worklog_batch({"rm_id": "70", "items": ITEMS})))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests lot worklog RM2716 passent")
