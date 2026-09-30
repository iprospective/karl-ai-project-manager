#!/usr/bin/env python3
"""Tests RM3369 — les deux routes de santé PM du serveur.

On vérifie ce que le cockpit va réellement recevoir : un badge qui compte les
soucis majeurs, une page qui porte les familles et la fraîcheur. Le point qui
compte le plus est le silence : **l'absence de rapport doit se voir**. Un badge
à zéro parce que plus rien ne calcule ment plus qu'il n'informe.

Lancer : python3 scripts/test_karl_agent_pmhealth.py
"""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core          # noqa: E402

hermetic_core()

spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

import pm_health as H                            # noqa: E402

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def with_report(payload):
    """Pose un rapport à l'emplacement que lit le serveur, et le rend."""
    path = pathlib.Path(os.environ["PM_HEALTH_REPORT"])
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


GROUPS_SAINS = [{"name": "Champs Redmine",
                 "checks": [H.chk("pisceen/dolibarr", "ok", "20 champ(s)")]}]
GROUPS_ROUGES = [
    {"name": "Champs Redmine",
     "checks": [H.chk("calicote/dolibarr", "error", "8 champ(s) non activés", "cocher le projet")]},
    {"name": "Normes", "checks": [H.chk("index", "warn", "périmé", "pm-norms-assemble")]},
]

with tempfile.TemporaryDirectory() as td:
    os.environ["PM_HEALTH_REPORT"] = str(pathlib.Path(td) / "pm-health.json")

    # 1. Aucun rapport du tout — le cas qui doit CRIER, pas se taire.
    chk = ka.op_pm_health_check({})
    check("sans rapport, le badge signale un souci majeur", chk["major"] >= 1)
    check("sans rapport, le pire niveau est error", chk["worst"] == "error")
    check("sans rapport, la ligne dit comment en produire un",
          any("pm-health" in i["fix"] for i in chk["items"]))
    st = ka.op_pm_health_status()
    check("sans rapport, la page porte quand même la famille Rapport",
          any(g["name"] == "Rapport" for g in st["groups"]))

    # 2. Rapport frais et sain — aucun badge.
    with_report({"generated_at": time.time(), "generated_label": "2026-09-30T10:00:00",
                 "groups": GROUPS_SAINS, "summary": H.health_summary(GROUPS_SAINS)})
    chk = ka.op_pm_health_check({})
    check("parc sain : aucun souci majeur", chk["major"] == 0)
    check("parc sain : rien à montrer", chk["count"] == 0)
    check("parc sain : le pire niveau est ok", chk["worst"] == "ok")
    st = ka.op_pm_health_status()
    check("la page rend les familles du rapport",
          [g["name"] for g in st["groups"]] == ["Champs Redmine", "Rapport"])
    check("la page date le rapport", bool(st["generated_label"]))
    check("la fraîcheur d'un rapport récent est verte",
          st["groups"][-1]["checks"][0]["level"] == "ok")

    # 3. Rapport frais et rouge — le badge compte les majeurs, pas les avertissements.
    with_report({"generated_at": time.time(), "generated_label": "2026-09-30T10:00:00",
                 "groups": GROUPS_ROUGES, "summary": H.health_summary(GROUPS_ROUGES)})
    chk = ka.op_pm_health_check({})
    check("un champ non activé compte pour un majeur", chk["major"] == 1)
    check("l'avertissement reste visible sans gonfler le compteur", chk["count"] == 2)
    check("l'erreur passe en tête", chk["items"][0]["level"] == "error")
    check("la remédiation voyage jusqu'au front", chk["items"][0]["fix"] == "cocher le projet")
    st = ka.op_pm_health_status()
    check("le résumé de la page compte l'erreur", st["summary"]["counts"]["error"] == 1)

    # 4. Rapport vieux de deux jours — le contenu était vert, le rapport ne l'est plus.
    with_report({"generated_at": time.time() - 48 * 3600, "generated_label": "avant-hier",
                 "groups": GROUPS_SAINS, "summary": H.health_summary(GROUPS_SAINS)})
    chk = ka.op_pm_health_check({})
    check("un rapport périmé devient lui-même un souci majeur", chk["major"] == 1)
    check("le souci de péremption nomme sa famille",
          any(i["family"] == "Rapport" for i in chk["items"]))

    # 5. Rapport illisible — on ne sert pas une exception au navigateur.
    pathlib.Path(os.environ["PM_HEALTH_REPORT"]).write_text("{{{", encoding="utf-8")
    chk = ka.op_pm_health_check({})
    check("un rapport corrompu se comporte comme un rapport absent", chk["major"] >= 1)
    check("un rapport corrompu ne lève pas côté page",
          isinstance(ka.op_pm_health_status().get("groups"), list))

    # 6. Ce que le contrat d'API promet au front.
    check("le badge rend toujours les clés attendues",
          {"items", "count", "major", "worst"} <= set(ka.op_pm_health_check({})))
    check("la page rend toujours les clés attendues",
          {"groups", "summary", "generated_at"} <= set(ka.op_pm_health_status()))
    check("tout est sérialisable en JSON",
          bool(json.dumps(ka.op_pm_health_status()) and json.dumps(ka.op_pm_health_check({}))))

    os.environ.pop("PM_HEALTH_REPORT", None)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("✓ tous les contrôles passent")
