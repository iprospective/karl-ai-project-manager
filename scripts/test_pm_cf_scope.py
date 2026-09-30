#!/usr/bin/env python3
"""Tests RM3368 — portée des champs par tracker, et refus d'écriture.

Ce qui est en jeu : Redmine accepte l'écriture d'un champ que le tracker ne
porte pas, puis la jette, en répondant « succès ». RM3224 a ainsi gardé 2 459
caractères d'étude invisibles neuf jours.

Deux propriétés à tenir ensemble, et la seconde est la plus facile à perdre :

1. le garde-fou **refuse** un champ de code sur un tracker qui n'en veut pas ;
2. il **ne bloque rien d'autre** — ni un champ légitime, ni un cas où l'on ne
   sait pas. Un garde-fou qui bloque sur une panne de lecture ferait plus de mal
   que le trou qu'il bouche.

Aucun réseau : la table de portée est injectée.

Lancer : python3 scripts/test_pm_cf_scope.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pm_cf_scope as S          # noqa: E402

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# La configuration réelle de l'instance, en miniature.
SCOPE = {
    3: ["Anomalie", "Evolution", "Tâche"],          # GIT Branche
    31: ["Anomalie", "Evolution", "Tâche"],         # Proposition d'implémentation
    5: ["Anomalie", "Evolution", "Tâche"],          # ROI — pas un champ de code
    33: ["Anomalie", "Evolution", "Assistance", "Tâche"],   # Critères d'acceptation
    15: None,                                        # portée inconnue
}

# ── lecture de la portée ────────────────────────────────────────────────────
API = {"custom_fields": [
    {"id": 3, "name": "GIT Branche", "customized_type": "issue",
     "trackers": [{"id": 1, "name": "Anomalie"}, {"id": 4, "name": "Tâche"}]},
    {"id": 16, "name": "Tokens", "customized_type": "time_entry",
     "trackers": []},
    {"id": 33, "name": "Critères", "customized_type": "issue", "trackers": None},
]}
sc = S.scope_from_api(API)
check("la portée se lit depuis l'API", sc[3] == ["Anomalie", "Tâche"])
check("les champs de time_entry sont écartés", 16 not in sc)
check("une portée absente donne None, pas une liste vide", sc[33] is None)
check("une réponse vide ne casse rien", S.scope_from_api({}) == {})
check("une réponse None ne casse rien", S.scope_from_api(None) == {})

REF = {"custom_fields": {
    3: {"name": "GIT Branche", "type": "issue", "trackers": ["bugfix", "feature", "autre"]},
    33: {"name": "Critères", "type": "issue", "trackers": None},
    16: {"name": "Tokens", "type": "time_entry", "trackers": None},
}}
rf = S.scope_from_reference(REF)
check("le repli hors ligne traduit les noms PM vers ceux de Redmine",
      rf[3] == ["Anomalie", "Evolution", "Tâche"])
check("le repli écarte aussi les time_entry", 16 not in rf)
check("le repli garde None pour une portée non dite", rf[33] is None)

# ── ce qui est permis ───────────────────────────────────────────────────────
check("champ de code sur Tâche : permis", S.field_allowed(SCOPE, 3, "Tâche"))
check("champ de code sur Assistance : refusé", not S.field_allowed(SCOPE, 3, "Assistance"))
check("critères d'acceptation sur Assistance : permis (le tracker les porte)",
      S.field_allowed(SCOPE, 33, "Assistance"))
check("portée inconnue : on laisse passer", S.field_allowed(SCOPE, 15, "Assistance"))
check("champ inconnu de la table : on laisse passer", S.field_allowed(SCOPE, 999, "Assistance"))
check("cf_id absent : on laisse passer", S.field_allowed(SCOPE, None, "Assistance"))
check("tracker inconnu : on laisse passer", S.field_allowed(SCOPE, 3, ""))
check("table vide : on laisse passer", S.field_allowed({}, 3, "Assistance"))

# ── le message de refus ─────────────────────────────────────────────────────
msg = S.refus_message("GIT Branche", "Assistance", 3224, SCOPE[3])
check("le refus nomme le champ et le tracker", "GIT Branche" in msg and "Assistance" in msg)
check("le refus dit que la valeur serait JETÉE", "JETTERAIT" in msg)
check("le refus cite l'incident fondateur", "RM3224" in msg)
check("le refus donne la commande de requalification", "pm-task-type-update.py 3224" in msg)
check("le refus donne l'autre issue : un ticket lié", "--parent 3224" in msg)
check("le refus renvoie à la norme", "methodes-travail" in msg)
check("le refus dit où le champ existe", "Anomalie, Evolution, Tâche" in msg)
check("un refus sans id reste lisible", "<id>" in S.refus_message("GIT PR", "Assistance"))

# ── check_write : deux sévérités ────────────────────────────────────────────
vrai_load, vrai_tracker = S.load_scope, S.issue_tracker
S.load_scope = lambda force=False: SCOPE
try:
    S.issue_tracker = lambda rm: "Assistance"
    # 1. champ de code → refus net
    try:
        S.check_write(3224, 3, "GIT Branche")
        check("un champ de code sur Assistance lève", False)
    except S.FieldNotOnTracker as e:
        check("un champ de code sur Assistance lève", True)
        check("l'exception porte le champ et le tracker",
              e.cf_name == "GIT Branche" and e.tracker == "Assistance")
    # 2. champ légitime → rien
    check("un champ porté par le tracker passe", S.check_write(3224, 33, "Critères") is True)
    # 3. autre champ indisponible → refus DOUX, sans exception
    #    (le ROI d'une assistance est légitime : le remède est d'activer le champ,
    #    pas de requalifier le ticket — bloquer ici casserait une estimation)
    check("un champ non-code indisponible n'est pas écrit, mais ne lève pas",
          S.check_write(3224, 5, "ROI") is False)
    # 4. tracker qui porte tout → rien ne bloque
    S.issue_tracker = lambda rm: "Tâche"
    check("sur Tâche, un champ de code passe", S.check_write(1, 3, "GIT Branche") is True)
    # 5. tracker illisible → on ne bloque pas
    S.issue_tracker = lambda rm: None
    check("tracker illisible : on laisse passer", S.check_write(1, 3, "GIT Branche") is True)
    # 6. interrupteur de secours
    S.issue_tracker = lambda rm: "Assistance"
    os.environ["PM_CF_SCOPE_OFF"] = "1"
    check("PM_CF_SCOPE_OFF désarme le garde-fou", S.check_write(1, 3, "GIT Branche") is True)
    os.environ.pop("PM_CF_SCOPE_OFF")
    # 7. le tracker fourni par l'appelant évite la lecture
    appels = []
    S.issue_tracker = lambda rm: appels.append(rm) or "Tâche"
    S.check_write(1, 3, "GIT Branche", tracker_name="Tâche")
    check("un tracker fourni évite d'interroger l'API", appels == [])
finally:
    S.load_scope, S.issue_tracker = vrai_load, vrai_tracker

# ── la mémorisation sur disque ──────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    os.environ["PM_CF_SCOPE_CACHE"] = str(Path(td) / "cf-scope.json")
    S._mem.update({"at": 0.0, "data": None})
    S._write_cache({3: ["Tâche"]})
    check("le cache s'écrit", Path(os.environ["PM_CF_SCOPE_CACHE"]).is_file())
    check("le cache se relit avec des clés entières", S._read_cache() == {3: ["Tâche"]})
    # un cache trop vieux ne doit pas servir : la config Redmine change à la main
    Path(os.environ["PM_CF_SCOPE_CACHE"]).write_text(
        json.dumps({"fetched_at": time.time() - S.CACHE_TTL - 10, "scope": {"3": ["Tâche"]}}),
        encoding="utf-8")
    check("un cache périmé est ignoré", S._read_cache() is None)
    Path(os.environ["PM_CF_SCOPE_CACHE"]).write_text("{{{", encoding="utf-8")
    check("un cache corrompu est ignoré, sans lever", S._read_cache() is None)
    os.environ.pop("PM_CF_SCOPE_CACHE")
    S._mem.update({"at": 0.0, "data": None})

# ── cohérence ───────────────────────────────────────────────────────────────
check("les champs de code sont nommés comme dans Redmine",
      "GIT Branche" in S.CODE_FIELD_NAMES and "Proposition d'implémentation" in S.CODE_FIELD_NAMES)
check("le ROI n'est PAS traité comme un champ de code", "ROI" not in S.CODE_FIELD_NAMES)
check("les critères d'acceptation non plus",
      "Critères d'acceptation" not in S.CODE_FIELD_NAMES)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("✓ tous les contrôles passent")
