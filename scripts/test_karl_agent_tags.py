#!/usr/bin/env python3
"""Tests RM2830 — étiquettes dans le cockpit : inventaire et règle de jeu.

Ce qui est protégé ici :
  1. l'inventaire des étiquettes en usage (`tags_in_use`) est trié par usage
     puis alphabétiquement — un ordre instable rendrait le menu illisible d'un
     rafraîchissement à l'autre ;
  2. la casse et les doublons ne créent pas deux entrées : le vocabulaire est
     normalisé comme à l'écriture (pm_tags) ;
  3. une règle de jeu dérivé « étiquette » ne retient que les sessions dont le
     TICKET la porte — et une session sans ticket ne matche jamais par erreur.

Lancer : python3 scripts/test_karl_agent_tags.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core          # noqa: E402

hermetic_core()

_spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(_spec)
sys.modules["karl_agent"] = ka
_spec.loader.exec_module(ka)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# — inventaire —
inv = ka.tags_in_use([
    {"tags": ["front", "refacto"]},
    {"tags": ["front", "bdd"]},
    {"tags": ["front"]},
    {"tags": []},
    {},
])
check("usage décroissant, puis alphabétique",
      [t["tag"] for t in inv] == ["front", "bdd", "refacto"], inv)
check("compte exact", [t["count"] for t in inv] == [3, 1, 1], inv)
check("casse et doublons fusionnés (même vocabulaire qu'à l'écriture)",
      ka.tags_in_use([{"tags": ["Front", "front", "FRONT"]}]) == [{"tag": "front", "count": 1}],
      ka.tags_in_use([{"tags": ["Front", "front", "FRONT"]}]))
check("aucune tâche → inventaire vide", ka.tags_in_use([]) == [])

# — règle de jeu dérivé « étiquette » —
TAGS = {"2816": ["front", "refacto"], "2822": ["bdd"]}
ka._sid_tags = lambda sid: TAGS.get(str(sid), [])          # isole du disque
k = {"cwd": "/w/x", "session_id": "s1"}
check("règle tag : la session du ticket étiqueté matche",
      ka._rule_matches({"tag": "front"}, "2816", k))
check("règle tag : un autre ticket ne matche pas",
      not ka._rule_matches({"tag": "front"}, "2822", k))
check("règle tag : une session sans ticket ne matche jamais",
      not ka._rule_matches({"tag": "front"}, "cockpit", k))
check("règle tag : normalisée comme le reste (Front == front)",
      ka._rule_matches({"tag": "Front"}, "2816", k))

# — validation de la règle —
check("« tag » est un critère accepté", ka._rule_norm({"tag": "front"}) == {"tag": "front"})
try:
    ka._rule_norm({"nawak": "x"})
    check("critère inconnu toujours refusé", False, "aucune erreur levée")
except ka.ApiError as e:
    check("critère inconnu toujours refusé", e.code == 400, e)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests étiquettes cockpit (RM2830) passent")
