#!/usr/bin/env python3
"""Tests RM2833 — routage étiquette → rôle d'agent.

Ce qui compte : la cascade client → projet, un départage STABLE quand plusieurs
étiquettes routent, un rôle inconnu qui se VOIT, et — le plus important — le fait
que rien ici n'assigne quoi que ce soit : on ne rend qu'une suggestion.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pm_roles

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


CLIENT = {"tag_roles": {"front": "dev", "bdd": "db", "infra": "infra"}}
PROJET = {"tag_roles": {"bdd": "analyst"}}          # le projet surcharge son client

t = pm_roles.merge_table(CLIENT, PROJET)
check("cascade : le projet surcharge le client", t["bdd"] == "analyst", t)
check("cascade : ce que le projet ne dit pas reste celui du client", t["front"] == "dev", t)
check("clés normalisées comme les étiquettes",
      pm_roles.merge_table({"tag_roles": {"Tunnel De Commande": "dev"}}, None)
      == {"tunnel-de-commande": "dev"})
check("table absente ou mal formée → table vide, pas d'exception",
      pm_roles.merge_table(None, None) == {} and pm_roles.merge_table({"tag_roles": "x"}, None) == {})

role, why = pm_roles.suggest(["front"], t)
check("suggestion simple", role == "dev" and "front" in why, (role, why))
check("la casse de l'étiquette ne change rien", pm_roles.suggest(["FRONT"], t)[0] == "dev")

role2, why2 = pm_roles.suggest(["front", "bdd"], t)
check("départage STABLE (alphabétique) quand deux étiquettes routent",
      role2 == "analyst" and pm_roles.suggest(["bdd", "front"], t)[0] == "analyst", (role2, why2))
check("…et les autres candidates sont NOMMÉES, pas tues silencieusement",
      "front" in why2, why2)

r3, why3 = pm_roles.suggest(["marketing"], t)
check("aucune étiquette ne route → pas de suggestion, avec la raison",
      r3 is None and "route" in why3, why3)
r4, why4 = pm_roles.suggest(["front"], {})
check("pas de table → on le dit (la conf manque, ce n'est pas la faute du ticket)",
      r4 is None and "tag_roles" in why4, why4)
r5, why5 = pm_roles.suggest([], t)
check("ticket sans étiquette → pas de suggestion", r5 is None)

r6, why6 = pm_roles.suggest(["x"], {"x": "nawak"})
check("rôle inconnu : suggéré MAIS signalé (un worker-nawak.md n'existe pas)",
      r6 == "nawak" and "inconnu" in why6, why6)
check("chemin du fichier de rôle", pm_roles.agent_file("db") == "agents/worker-db.md")

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests routage par étiquette (RM2833) passent")
