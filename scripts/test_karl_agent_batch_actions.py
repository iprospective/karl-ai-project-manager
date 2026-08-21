#!/usr/bin/env python3
"""Tests RM2786 — quelles actions de lot ont un sens pour une sélection.

Le cockpit affichait ses quatre boutons de lot dès qu'un ticket était coché,
sans regarder ni le statut ni l'existence d'une MR : « merger » sur un lot sans
MR, « à tester » sur un ticket déjà chez le demandeur, « traiter » sur un ticket
fermé. Un bouton qui ne peut rien faire coûte deux fois — on le lit, puis on
finit par l'essayer.

Ces tests fixent la règle CÔTÉ SERVEUR, seule source de vérité : le cockpit la
lit (`/cockpit-config`), il ne la redéclare pas.

Lancer : python3 scripts/test_karl_agent_batch_actions.py
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


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# — le mode « analyser » existe et ne recouvre QUE l'étude —
check("le mode `etudier` est déclaré", "etudier" in ka.BATCH_MODES)
etu = ka.BATCH_MODES["etudier"]["actions"]
check("il couvre les trois statuts d'étude",
      set(etu) == {"nouveau", "a_etudier_chiffrer", "etude_chiffrage_en_cours"})
check("…et rien d'autre : pas de réalisation",
      "a_faire" not in etu and "en_cours" not in etu)
skip_etu = ka.BATCH_MODES["etudier"]["skip"]
check("une étude déjà rendue est écartée AVEC sa raison",
      "etude_chiffrage_a_valider" in skip_etu and skip_etu["etude_chiffrage_a_valider"])
check("un ticket livré aussi", "a_tester_demandeur" in skip_etu)

# — comptes par mode : ce qui décide des boutons —
n = ka.batch_modes_for(["a_faire", "en_cours", "a_tester_demandeur", "nouveau"])
check("« analyser » ne compte que le ticket à étudier", n["etudier"] == 1)
check("« traiter » compte les trois qui restent à faire", n["traiter"] == 3)
check("« à tester » ne compte que ce qui peut être livré", n["atester"] == 2)
check("« fermer » ne compte que le ticket livré", n["fermer"] == 1)

check("un lot entièrement livré ne propose ni analyse ni traitement",
      ka.batch_modes_for(["a_tester_demandeur", "a_mep"]) ==
      {"traiter": 0, "atester": 0, "etudier": 0, "fermer": 2})
check("un lot fermé ne propose plus rien",
      all(v == 0 for v in ka.batch_modes_for(["ferme", "ferme"]).values()))
check("sélection vide → aucun bouton",
      all(v == 0 for v in ka.batch_modes_for([]).values()))
check("liste absente tolérée", all(v == 0 for v in ka.batch_modes_for(None).values()))

# Un statut inconnu ne doit RIEN masquer : une action inatteignable parce qu'un
# statut a changé de nom est pire qu'un bouton de trop (le plan écarte ensuite).
inc = ka.batch_modes_for(["statut_invente_2786"])
check("un statut inconnu laisse toutes les actions proposées",
      all(v == 1 for v in inc.values()))
check("la casse n'entre pas en compte",
      ka.batch_modes_for(["A_FAIRE"])["traiter"] == 1)

# — « fermer » : seulement ce qui est livré —
check("les statuts fermables sont exactement les statuts livrés",
      ka.CLOSABLE_STATUSES == {"a_tester_dev", "a_tester_demandeur", "a_mep", "en_mep"})
check("un ticket en cours n'est pas fermable",
      ka.batch_modes_for(["en_cours"])["fermer"] == 0)

# — la règle est SERVIE, pas redéclarée côté cockpit —
cfg_modes = {name: {"statuses": sorted(m["actions"]), "skip": m["skip"]}
             for name, m in ka.BATCH_MODES.items()}
check("chaque mode servi porte ses statuts et ses raisons d'exclusion",
      all(v["statuses"] and v["skip"] for v in cfg_modes.values()))
check("les trois modes sont exposés",
      set(cfg_modes) == {"traiter", "atester", "etudier"})

print()
if fails:
    print(f"ÉCHEC — {len(fails)} contrôle(s) : " + " · ".join(fails))
    sys.exit(1)
print("OK — actions de lot pertinentes (analyser, traiter, à tester, fermer)")
