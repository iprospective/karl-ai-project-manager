#!/usr/bin/env python3
"""Tests RM2840 — sémantique de synchronisation des tags.

Règle posée par le demandeur (2026-08-26) :

  · ajout      : bidirectionnel ;
  · suppression PM → Redmine : oui ;
  · suppression Redmine → PM : **uniquement si le tag a été supprimé dans
    Redmine**. Jamais par simple absence lors d'un refresh.

Le dernier point est le seul qui demande de l'information : « absent » ne veut
pas dire « retiré ». Elle vient des journaux Redmine, qui émettent une entrée par
valeur pour un CF multiple (`old_value=45, new_value=null` = retrait). Sans
journal exploitable, on retombe sur l'additif — le repli explicitement accepté.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_tags

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# — RELECTURE (Redmine → PM) —
# 1. le cas que le demandeur refuse : un mot-clé local sans équivalent CF
p = pm_tags.pull_plan(["cockpit", "front"], ["front"], [])
check("un refresh n'efface PAS un mot-clé local sans équivalent",
      p["tags"] == ["cockpit", "front"] and not p["supprimes"], p)
# 2. ajout côté Redmine → arrive en local
p = pm_tags.pull_plan(["cockpit"], ["front"], [])
check("un tag ajouté dans Redmine descend en local",
      p["tags"] == ["cockpit", "front"] and p["ajouts"] == ["front"], p)
# 3. suppression RÉELLE côté Redmine (vue au journal) → appliquée
p = pm_tags.pull_plan(["cockpit", "front"], [], ["front"])
check("un tag supprimé dans Redmine est retiré en local",
      p["tags"] == ["cockpit"] and p["supprimes"] == ["front"], p)
# 4. supprimé PUIS re-ajouté entre deux synchros : il reste
p = pm_tags.pull_plan(["front"], ["front"], ["front"])
check("supprimé puis re-ajouté : il reste (l'état courant prime sur l'historique)",
      p["tags"] == ["front"] and not p["supprimes"], p)
# 5. le journal parle d'un tag qu'on n'a pas : rien à faire
p = pm_tags.pull_plan(["cockpit"], [], ["front"])
check("un retrait qui ne concerne pas nos tags ne fait rien",
      p["tags"] == ["cockpit"] and not p["supprimes"], p)
# 6. repli : aucun journal exploitable → additif strict
p = pm_tags.pull_plan(["cockpit", "front"], ["db"], None)
check("sans journal exploitable, la synchro est ADDITIVE (aucune suppression)",
      p["tags"] == ["cockpit", "db", "front"] and not p["supprimes"], p)
check("…et le repli est signalé, pas silencieux", p["additif"] is True, p)

# — ÉCRITURE (PM → Redmine) —
# 7. retrait local explicite → poussé
w = pm_tags.push_plan(["front", "db"], ["front"], ["front", "db"])
check("un tag retiré en local est retiré côté Redmine",
      w["cf"] == ["front"] and w["retires"] == ["db"], w)
# 8. le piège : une valeur ajoutée dans l'UI ne doit pas être écrasée
w = pm_tags.push_plan(["front"], ["front", "db"], ["front", "design"])
check("une valeur ajoutée côté Redmine survit à une écriture locale",
      w["cf"] == ["db", "design", "front"], w)
check("…et elle descend dans le frontmatter (parité)",
      w["local"] == ["db", "design", "front"], w)
# 9. retrait local d'un tag présent des deux côtés : il part quand même
w = pm_tags.push_plan(["front", "db"], ["front"], ["front", "db", "design"])
check("le retrait local l'emporte sur la présence distante",
      "db" not in w["cf"] and "design" in w["cf"], w)
# 10. un mot-clé local n'a rien à faire dans le payload CF
w = pm_tags.push_plan([], ["cockpit", "front"], [])
check("le plan CF ne contient que ce qui est poussable",
      w["cf"] == ["cockpit", "front"], w)   # le filtrage par registre se fait au payload

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests synchro des tags (RM2840) passent")
