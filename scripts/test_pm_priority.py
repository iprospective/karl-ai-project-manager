#!/usr/bin/env python3
"""Tests RM3275 — l'énumération `priority`, source unique et extensible.

Ce qui doit tenir : une seule table, lue de `redmine.reference.yml` ; l'ordre de
force déduit de l'id Redmine, jamais d'une liste parallèle ; les poids
historiques reproduits à l'identique, pour qu'aucun classement déjà rendu ne
bouge ; `immediat` au-dessus d'`urgent` partout — table, tri et poids ; et ce
qui n'est pas de l'énumération (« A définir », valeur inventée, champ vide) qui
ne s'intercale jamais au milieu d'une file.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


import pm_priority as P  # noqa: E402

print("[RM3275] la table vient de la référence, et immediat y est")
check("les cinq priorités sont connues",
      P.labels() == ["low", "normal", "high", "urgent", "immediat"], str(P.labels()))
check("immediat est bien l'id Redmine 5", P.to_id("immediat") == 5, str(P.to_id("immediat")))
check("les ids historiques n'ont pas bougé",
      [P.to_id(x) for x in ("low", "normal", "high", "urgent")] == [1, 2, 3, 4])
check("la table est lue du yml, pas du repli",
      P._ids_raw() is not P._FALLBACK_IDS and P._ids_raw() == P._FALLBACK_IDS)

print("\n[RM3275] l'ordre de force se déduit de l'id, immediat au sommet")
check("immediat est plus fort qu'urgent", P.rank("immediat") > P.rank("urgent"))
check("urgent reste plus fort que high", P.rank("urgent") > P.rank("high"))
check("labels_by_force part du plus fort", P.labels_by_force()[0] == "immediat")
tri = sorted(["normal", "immediat", "low", "urgent", "high"], key=P.sort_key)
check("une file se trie du plus prioritaire au moins",
      tri == ["immediat", "urgent", "high", "normal", "low"], str(tri))

print("\n[RM3275] les poids historiques sont reproduits, immediat les prolonge")
check("low 0.5 · normal 1 · high 2 · urgent 4",
      [P.weight(x) for x in ("low", "normal", "high", "urgent")] == [0.5, 1.0, 2.0, 4.0],
      str([P.weight(x) for x in ("low", "normal", "high", "urgent")]))
check("immediat pèse 8, le double d'urgent", P.weight("immediat") == 8.0, str(P.weight("immediat")))
check("weights() rend la table entière", P.weights()["immediat"] == 8.0 and len(P.weights()) == 5)

print("\n[RM3275] aller-retour sans perte")
for label in P.labels():
    check(f"{label} → id → {label}", P.from_id(P.to_id(label)) == label)

print("\n[RM3275] ce qui n'est pas de l'énumération ne s'intercale pas")
check("« A définir » (24) n'est pas une priorité", P.from_id(24) == "normal", P.from_id(24))
check("un id inconnu retombe sur le défaut", P.from_id(99) == "normal")
check("un id illisible aussi", P.from_id(None) == "normal" and P.from_id("x") == "normal")
check("une valeur inventée est refusée", not P.is_valid("immédiat-vraiment"))
check("une valeur vide est refusée", not P.is_valid("") and not P.is_valid(None))
check("normalize ramène au défaut", P.normalize("n'importe quoi") == "normal")
check("normalize tolère la casse et les espaces", P.normalize("  Immediat ") == "immediat")
check("to_id d'un inconnu ne rend pas un id au hasard", P.to_id("inconnu") == 2)
check("une priorité inconnue part en FIN de file, pas au milieu",
      P.sort_key("inconnue") > P.sort_key("low"))
check("un rang inconnu vaut -1", P.rank("inconnue") == -1)
check("mais son poids retombe sur celui du défaut", P.weight("inconnue") == P.weight("normal"))

print("\n[RM3275] le repli tient si la référence est illisible")
_load = sys.modules["redmine_utils"].load_reference if "redmine_utils" in sys.modules else None
import redmine_utils  # noqa: E402
redmine_utils.load_reference = lambda: (_ for _ in ()).throw(OSError("référence illisible"))
P.reset_cache()
check("sans référence, les cinq priorités restent connues",
      P.labels() == ["low", "normal", "high", "urgent", "immediat"], str(P.labels()))
check("et immediat garde son id", P.to_id("immediat") == 5)
if _load:
    redmine_utils.load_reference = _load
P.reset_cache()

print("\n[RM3275] la regex d'argument couvre les cinq")
check("choices_re les liste toutes",
      P.choices_re() == "low|normal|high|urgent|immediat", P.choices_re())

print()
if FAIL:
    print(f"✗ {len(FAIL)} test(s) en échec :")
    for f in FAIL:
        print(f"   · {f}")
    sys.exit(1)
print("✓ tous les tests passent")
