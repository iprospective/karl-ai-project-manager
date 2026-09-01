#!/usr/bin/env python3
"""Tests RM2701 — la MR de promotion ne doit pas écraser « GIT Branche ».

Le flux normal appelle `pm-mr create` DEUX fois : la MR du ticket
(`<id>-<slug>` → `dev`), puis la MR de promotion (`dev` → `main`). La seconde
écrasait le CF par `dev`, qui ne désigne rien — toutes les livraisons y passent.
Constaté sur #2635, #2659 et #2660, et de nature à re-casser les 81 CF
rétro-remplis par RM2592 au fil des promotions.

Lancer : python3 scripts/test_pm_mr_cf_branche.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_mr", HERE / "pm-mr.py")
mr = importlib.util.module_from_spec(spec)
sys.modules["pm_mr"] = mr
spec.loader.exec_module(mr)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# — ce qui EST la branche du ticket —
for rid, br in ((2701, "2701-pm-mr-la-mr-de-promotion-ecrase-git-bran"),
                ("2701", "2701-x"),
                (2659, "2659-cockpit-onglet-fichiers-racines-des-proj")):
    check("branche du ticket reconnue : %s" % str(br)[:34], mr.branche_de_ticket(rid, br))

# — ce qui ne l'est PAS : les branches d'intégration, et le piège du préfixe —
for br in ("dev", "main", "master", "preprod", "", None, "release/1.2"):
    check("branche d'intégration écartée : %r" % br, not mr.branche_de_ticket(2701, br))
check("un id qui n'est qu'un préfixe numérique ne suffit pas",
      not mr.branche_de_ticket(270, "2701-x"))
check("…dans l'autre sens non plus",
      not mr.branche_de_ticket(27011, "2701-x"))
check("il faut le tiret séparateur, pas seulement l'id",
      not mr.branche_de_ticket(2701, "2701x-quelque-chose"))
check("un id d'un autre ticket est refusé",
      not mr.branche_de_ticket(2701, "2659-autre-chose"))

# — le comportement observable : quels champs partent chez Redmine —
# On intercepte l'écriture plutôt que de la simuler : c'est le point exact où
# la régression s'était produite.
envoyés = []


class _FauxRedmine:
    @staticmethod
    def cf_id_by_name(name):
        return {"GIT Branche": 3, "GIT PR": 4}.get(name)

    @staticmethod
    def update_issue_fields(rm_id, custom_fields=None, **kw):
        envoyés.extend(custom_fields or [])
        return True, None


class _FauxProvider:
    @staticmethod
    def fetch_issue(rm_id):
        # relecture : renvoie ce qui vient d'être envoyé, pour que la
        # vérification interne de pm-mr soit satisfaite
        return {"custom_fields": [dict(c) for c in envoyés]}


sys.modules["redmine_utils"] = _FauxRedmine
mr.get_task_provider = lambda *a, **k: _FauxProvider

envoyés.clear()
mr._post_git_cf(2701, "2701-ma-branche", "https://forge/mr/1")
ids = {c["id"]: c["value"] for c in envoyés}
check("MR du ticket : la branche est posée", ids.get(3) == "2701-ma-branche")
check("MR du ticket : la PR aussi", ids.get(4) == "https://forge/mr/1")

envoyés.clear()
mr._post_git_cf(2701, "dev", "https://forge/mr/2")
ids = {c["id"]: c["value"] for c in envoyés}
check("MR de promotion : « GIT Branche » N'EST PAS envoyé", 3 not in ids)
check("MR de promotion : « GIT PR » l'est toujours", ids.get(4) == "https://forge/mr/2")
check("…et rien d'autre ne part", set(ids) == {4})

# Le scénario complet, dans l'ordre réel : ticket puis promotion.
envoyés.clear()
mr._post_git_cf(2701, "2701-ma-branche", "https://forge/mr/1")
posé = {c["id"]: c["value"] for c in envoyés}[3]
envoyés.clear()
mr._post_git_cf(2701, "dev", "https://forge/mr/2")
check("après la promotion, la branche du ticket n'a pas été remplacée",
      posé == "2701-ma-branche" and all(c["id"] != 3 for c in envoyés))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests CF branche de pm-mr RM2701 passent")
