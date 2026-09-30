#!/usr/bin/env python3
"""Tests RM3228 — le statut `etude_chiffrage_a_corriger` (Redmine 24 « Etude/CDC à corriger »).

Ce qui doit tenir : le statut est connu PARTOUT où un statut se lit (référence, repli, validation,
synchro depuis Redmine) ; il n'est atteignable que depuis l'étude à valider et ne mène qu'à sa reprise ;
le renvoi exige une note ; et le ticket revient à l'AUTEUR de l'étude — lu dans les journaux, jamais
deviné. Au passage, la table de synchro Redmine → NORMS dérive de la référence : elle avait dérivé.

Lancer : python3 scripts/test_pm_status_etude_a_corriger.py
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core           # noqa: E402

hermetic_core()                                  # AVANT l'import des modules PM
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def load(name, fname):
    spec = importlib.util.spec_from_file_location(name, str(HERE / fname))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


import redmine_utils                              # noqa: E402
ST = load("pm_task_status_update", "pm-task-status-update.py")
SY = load("pm_task_sync", "pm-task-sync.py")
VT = load("validate_task", "validate-task.py")
NOM = "etude_chiffrage_a_corriger"

print("[RM3228] le statut est connu partout")
check("référence : id Redmine 24", redmine_utils.status_ids().get(NOM) == 24, redmine_utils.status_ids().get(NOM))
check("repli sans référence : id 24 aussi", redmine_utils._FALLBACK_STATUS_IDS.get(NOM) == 24)
check("status_map (POST/PUT Redmine) le résout", redmine_utils.status_map().get(NOM) == 24)
check("validate-task l'accepte", NOM in VT.VALID_STATUSES)
check("pm-task-sync rapatrie un 24 posé dans l'UI Redmine", SY.REDMINE_TO_NORMS_STATUS.get(24) == NOM)

print("\n[RM3228] la table de synchro dérive de la référence (elle avait dérivé)")
check("20 = a_tester_preprod (RM2893), plus en_mep", SY.REDMINE_TO_NORMS_STATUS.get(20) == "a_tester_preprod")
check("22 = en_mep (RM2893)", SY.REDMINE_TO_NORMS_STATUS.get(22) == "en_mep")
check("23 = a_mep_prod (RM2926)", SY.REDMINE_TO_NORMS_STATUS.get(23) == "a_mep_prod")
check("tous les statuts de la référence sont rapatriables",
      all(SY.REDMINE_TO_NORMS_STATUS.get(i) == n for n, i in redmine_utils.status_ids().items()))
check("les ids dépréciés gardent leur raison de fermeture", SY.REDMINE_TO_NORMS_STATUS.get(5) == ("ferme", "resolu"))

print("\n[RM3228] transitions")
T = {k: [c for c, _ in v] for k, v in ST.NORMS_TRANSITIONS.items()}
check("on y entre depuis l'étude à valider", NOM in T["etude_chiffrage_a_valider"])
check("on n'y entre depuis nulle part ailleurs",
      [k for k, v in T.items() if NOM in v] == ["etude_chiffrage_a_valider"])
check("on en sort vers la reprise de l'étude", T.get(NOM) == ["etude_chiffrage_en_cours"])
check("la reprise directe de l'agent reste possible (RM2629)", "etude_chiffrage_en_cours" in T["etude_chiffrage_a_valider"])
cond = dict(ST.NORMS_TRANSITIONS["etude_chiffrage_a_valider"])[NOM]
check("le renvoi est marqué « note obligatoire » : le cockpit la demande", "note obligatoire" in cond)
src = (HERE / "pm-task-status-update.py").read_text(encoding="utf-8")
check("et le script la refuse sans note", "--note obligatoire pour renvoyer une étude" in src)
check("en_pause / ferme génériques : le statut n'est pas inactif", NOM not in ST.INACTIVE_STATUSES)

print("\n[RM3228] réattribution à l'auteur de l'étude")
def j(*details):
    return {"details": [dict(name=n, old_value=o, new_value=v) for n, o, v in details]}
soumis = [j(("status_id", "2", "14")),
          j(("status_id", "14", "21"), ("assigned_to_id", "79", "5"))]
check("l'assigné remplacé par la soumission est l'auteur", ST.study_author_uid(1, soumis) == 79)
preassigne = [j(("assigned_to_id", "12", "79")),                      # déverrouillage assignee-only
              j(("status_id", "14", "21"), ("assigned_to_id", "79", "5"))]
check("après un déverrouillage assignee-only : l'assigné juste avant la soumission",
      ST.study_author_uid(1, preassigne) == 79)
separe = [j(("assigned_to_id", "33", "79")), j(("status_id", "14", "21"))]
check("soumission sans changement d'assigné : on remonte au dernier changement", ST.study_author_uid(1, separe) == 33)
deux = [j(("status_id", "14", "21"), ("assigned_to_id", "40", "5")),
        j(("status_id", "21", "14"), ("assigned_to_id", "5", "79")),
        j(("status_id", "14", "21"), ("assigned_to_id", "79", "5"))]
check("plusieurs soumissions : la DERNIÈRE fait foi", ST.study_author_uid(1, deux) == 79)
check("jamais soumise : on ne devine pas", ST.study_author_uid(1, [j(("status_id", "1", "14"))]) is None)
check("aucun journal : on ne devine pas", ST.study_author_uid(1, []) is None)
check("introuvable ⇒ attribution conservée ET signalée", "auteur de l'étude introuvable" in src)

print("\n[RM3228] le reste du PM le connaît")
ka = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("lot « analyser » du cockpit : l'étude renvoyée se reprend", '"etude_chiffrage_a_corriger": ("etudier"' in ka)
check("lot « à tester » : elle est écartée avec sa raison", '"etude_chiffrage_a_corriger": "étude renvoyée' in ka)
import pm_worklog_states                           # noqa: E402
# RM3323 : un retour a sa propre section, « à corriger » — toujours du travail à reprendre, visible,
# mais plus noyé parmi ce que personne n'a encore commencé.
check("worklog : elle compte dans « à corriger » (travail à reprendre)",
      NOM in pm_worklog_states.FIX and pm_worklog_states.bucket(NOM) == "corriger")
check("registre des fonctionnalités : ticket « prévu »", NOM in load("pcf", "pm-cdc-features.py").PREVUS)
wf = (HERE.parent / "workflow.reference.yml").read_text(encoding="utf-8")
check("workflow.reference.yml porte la transition observée dans Redmine", NOM in wf)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — etude_chiffrage_a_corriger (RM3228)"))
sys.exit(1 if FAIL else 0)
