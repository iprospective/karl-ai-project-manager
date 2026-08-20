#!/usr/bin/env python3
"""Tests RM2698 — alertes de dérive.

Ce qu'on protège : une alerte doit être RARE, DATÉE et REPORTABLE. Les trois
échouent différemment — trop d'alertes et on ne les lit plus, pas de date et on
ne sait pas laquelle traiter, pas de report et on apprend à les ignorer.

Lancer : python3 scripts/test_karl_agent_alerts.py
"""
import importlib.util
import pathlib
import sys
import time

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


NOW = time.mktime(time.strptime("2026-08-18T12:00", "%Y-%m-%dT%H:%M"))

# — alert_age_days : formats PM, et refus de deviner —
check("horodatage complet", round(ka.alert_age_days("2026-08-11T12:00", NOW), 1) == 7.0)
check("date seule", round(ka.alert_age_days("2026-08-11", NOW), 1) == 7.5)
check("date absente → None (on n'invente pas d'ancienneté)",
      ka.alert_age_days("", NOW) is None and ka.alert_age_days(None, NOW) is None)
check("date illisible → None", ka.alert_age_days("hier", NOW) is None)
check("date future → 0, jamais négatif", ka.alert_age_days("2026-09-01", NOW) == 0.0)

TH = {"orphan_hours": 72, "mr_days": 7, "verdict_days": 14, "mep_days": 3, "max": 12}
PROJ = [{"client": "acme", "project": "shop", "tickets": [
    {"rm_id": "1", "status": "en_cours", "bucket": "active", "has_live_session": False,
     "updated": "2026-08-01", "title": "orphelin"},
    {"rm_id": "2", "status": "en_cours", "bucket": "active", "has_live_session": True,
     "updated": "2026-08-01", "title": "suivi"},
    {"rm_id": "3", "status": "en_cours", "bucket": "active", "has_live_session": False,
     "updated": "2026-08-17", "title": "récent"},
    {"rm_id": "4", "status": "a_tester_demandeur", "bucket": "waiting",
     "updated": "2026-07-01", "title": "verdict vieux"},
    {"rm_id": "5", "status": "a_tester_demandeur", "bucket": "waiting",
     "updated": "2026-08-15", "title": "verdict récent"},
    {"rm_id": "6", "status": "a_mep", "bucket": "waiting", "updated": "2026-08-01", "title": "à déployer"},
    {"rm_id": "7", "status": "en_cours", "bucket": "active", "has_live_session": False, "title": "sans date"},
], "mrs": [
    {"iid": "9", "repo": "r", "ref": "RM1", "ts": "2026-07-20T10:00", "url": "u"},
    {"iid": "10", "repo": "r", "ref": "RM2", "ts": "2026-08-17T10:00"},
]}]

res = ka.build_alerts(PROJ, TH, NOW)
kinds = {a["key"]: a["kind"] for a in res["alerts"]}
check("ticket actif sans session, au-delà du seuil → alerte", kinds.get("t:1") == "orphan")
check("…mais pas s'il a une session vivante", "t:2" not in kinds)
check("…ni s'il est récent (72 h)", "t:3" not in kinds)
check("verdict qui traîne → alerte", kinds.get("t:4") == "verdict")
check("verdict récent → silence", "t:5" not in kinds)
check("validé non déployé → alerte", kinds.get("t:6") == "mep")
check("ticket sans date : jamais d'alerte inventée", "t:7" not in kinds)
check("MR ancienne → alerte", kinds.get("m:r:9") == "mr")
check("MR d'hier → silence", "m:r:10" not in kinds)
check("chaque alerte porte son ÂGE", all(a.get("age_days") for a in res["alerts"]))
check("la plus ancienne en tête",
      [a["key"] for a in res["alerts"]][:2] == ["t:4", "m:r:9"], str([a["key"] for a in res["alerts"]]))

# — plafond : borné ET annoncé —
gros = [{"client": "c", "project": "p", "mrs": [], "tickets": [
    {"rm_id": str(100 + i), "status": "a_tester_demandeur", "bucket": "waiting",
     "updated": "2026-06-01", "title": "t"} for i in range(30)]}]
capped = ka.build_alerts(gros, TH, NOW)
check("liste bornée", len(capped["alerts"]) == 12)
check("total réel conservé", capped["total"] == 30)
check("ce qui est masqué est COMPTÉ", capped["hidden"] == 18)

# — report : décale, ne supprime pas —
snoozed = ka.build_alerts(PROJ, TH, NOW, {"t:4": NOW + 86400})
check("une alerte reportée disparaît de la liste", "t:4" not in {a["key"] for a in snoozed["alerts"]})
check("…et les autres restent", len(snoozed["alerts"]) == len(res["alerts"]) - 1)

# — seuils : réglables, et jamais 0 (0 = alerter sur tout) —
th2 = dict(TH, verdict_days=60)
check("relever le seuil fait taire l'alerte",
      "t:4" not in {a["key"] for a in ka.build_alerts(PROJ, th2, NOW)["alerts"]})
check("entrées vides tolérées", ka.build_alerts(None, TH, NOW)["total"] == 0)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests alertes de dérive RM2698 passent")
