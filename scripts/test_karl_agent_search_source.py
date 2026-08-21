#!/usr/bin/env python3
"""Tests RM2770 — recherche de ticket : source locale, Redmine, ou les deux.

Ce qui est protégé ici, dans l'ordre d'importance :
  1. une panne Redmine ne fait JAMAIS disparaître les résultats locaux — c'est
     la raison d'être du champ `error` séparé ;
  2. `redmine_utils` signale ses erreurs par `sys.exit()`, donc par `SystemExit`,
     qui ne dérive pas d'`Exception` : non capturé, il tuerait la requête sans
     réponse (le mécanisme exact de RM2749) ;
  3. la fusion ne duplique pas un ticket présent des deux côtés, et garde les
     données LOCALES — le MD est ce que le système édite.

Lancer : python3 scripts/test_karl_agent_search_source.py
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


# — fusion des deux sources —
LOC = [{"rm_id": "10", "title": "local dix", "status": "a_faire", "client": "c", "project": "p"},
       {"rm_id": "8", "title": "local huit", "status": "ferme", "client": "c", "project": "p"}]
DIST = [{"rm_id": "10", "title": "Redmine dix", "status": "New", "origin": "redmine",
         "synced": True, "assigned_to": "Karl", "updated_on": "2026-08-21"},
        {"rm_id": "99", "title": "jamais fetché", "status": "New", "origin": "redmine",
         "synced": False, "assigned_to": "Karl"}]

m = ka.merge_search_results(LOC, DIST)
check("aucun doublon quand un ticket est des deux côtés", len(m) == 3)
check("tri par id décroissant", [r["rm_id"] for r in m] == ["99", "10", "8"])
dix = next(r for r in m if r["rm_id"] == "10")
check("le MD fait foi : le titre local est conservé", dix["title"] == "local dix")
check("…et son statut NORMS aussi", dix["status"] == "a_faire")
check("le ticket commun est marqué « both »", dix["origin"] == "both")
check("…enrichi de ce que seul Redmine sait", dix["assigned_to"] == "Karl")
seul = next(r for r in m if r["rm_id"] == "99")
check("un ticket jamais fetché apparaît, marqué non synchronisé",
      seul["origin"] == "redmine" and seul["synced"] is False)
check("un résultat local est toujours « synced »",
      all(r["synced"] for r in m if r["origin"] == "local"))
check("sources vides tolérées", ka.merge_search_results([], []) == []
      and ka.merge_search_results(None, None) == [])
check("les entrées d'origine ne sont pas mutées",
      LOC[0].get("origin") is None and "synced" not in LOC[0])

# — la panne Redmine ne doit rien emporter —
import redmine_utils as ru                       # noqa: E402

_vrai_list = ru.list_issues


def _boom_exit(*a, **k):
    sys.exit("ERREUR Redmine HTTP 401 sur /issues : Unauthorized")


def _boom_exc(*a, **k):
    raise ConnectionError("connexion refusée")


try:
    ru.list_issues = _boom_exit
    r = ka.op_search_redmine("test")
    check("un sys.exit de redmine_utils est rattrapé (pas de requête sans réponse)",
          r["results"] == [] and "401" in (r["error"] or ""))
    ru.list_issues = _boom_exc
    r = ka.op_search_redmine("test")
    check("une erreur réseau est rattrapée aussi",
          r["results"] == [] and "ConnectionError" in (r["error"] or ""))

    # — mapping des résultats —
    def _fake(params=None, limit=None, timeout=None):
        _fake.params = dict(params or {})
        return [{"id": 4242, "subject": "Sujet distant",
                 "status": {"name": "Nouveau"}, "priority": {"name": "Normal"},
                 "project": {"name": "Projet X"}, "assigned_to": {"name": "Karl"},
                 "updated_on": "2026-08-21T10:00:00Z"},
                {"subject": "sans id — ignoré"}]

    ru.list_issues = _fake
    r = ka.op_search_redmine("sujet")
    check("un résultat Redmine est normalisé au format des résultats locaux",
          len(r["results"]) == 1 and r["results"][0]["rm_id"] == "4242")
    check("…et porte son origine et son état de synchro",
          r["results"][0]["origin"] == "redmine" and r["results"][0]["synced"] is False)
    check("une issue sans id est ignorée plutôt que rendue à moitié",
          all(x["rm_id"] for x in r["results"]))
    check("une requête texte cherche « contient » dans le sujet",
          _fake.params.get("subject") == "~sujet")
    check("sans filtre de statut, Redmine ne se limite pas aux tickets OUVERTS",
          _fake.params.get("status_id") == "*")
    ka.op_search_redmine("4242")
    check("une requête numérique cherche par ID, pas en plein texte",
          _fake.params.get("issue_id") == "4242" and "subject" not in _fake.params)
    ka.op_search_redmine("x", status="a_faire")
    check("un statut NORMS est traduit en id Redmine",
          str(_fake.params.get("status_id")).isdigit())
    ka.op_search_redmine("x", status="statut_qui_nexiste_pas")
    check("un statut inconnu ne filtre rien plutôt que de tout masquer",
          _fake.params.get("status_id") == "*")
finally:
    ru.list_issues = _vrai_list

print()
if fails:
    print(f"ÉCHEC — {len(fails)} contrôle(s) : " + " · ".join(fails))
    sys.exit(1)
print("OK — recherche multi-source (fusion, panne Redmine, mapping)")
