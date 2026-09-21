#!/usr/bin/env python3
"""Tests RM3175 — /resolve porte ce que les onglets Critères · Implémentation · Déploiement affichent.

Les critères passent par la fonction de lecture unique de RM2882 (`pm_acceptance.criteria_text`) :
champ dédié s'il est rempli, section de la description sinon — et la PROVENANCE est rendue, parce
qu'elle décide de l'outil avec lequel on coche.

Lancer : python3 scripts/test_karl_agent_resolve_tabs.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.argv = [sys.argv[0]]
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def chk(label, cond):
    print(("✓ " if cond else "✗ ") + label)
    if not cond:
        fails.append(label)


BODY = "## Contexte\n\nx\n\n## Critères d'acceptation\n\n- [x] depuis la description\n- [ ] second\n"
a = ka._ticket_acceptance({}, BODY)
chk("ticket non migré : critères lus dans la description", a["source"] == "description" and len(a["items"]) == 2)
chk("… avec leur coche", a["items"][0] == {"done": True, "label": "depuis la description"})
a = ka._ticket_acceptance({"acceptance": "- [ ] depuis le champ"}, BODY)
chk("ticket migré : le champ dédié fait foi", a["source"] == "acceptance" and [i["label"] for i in a["items"]] == ["depuis le champ"])
a = ka._ticket_acceptance({}, "## Contexte\n\nrien\n")
chk("aucun critère : source None et liste vide, jamais d'erreur", a["source"] is None and a["items"] == [])

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — /resolve et les onglets de la fiche (RM3175)")
