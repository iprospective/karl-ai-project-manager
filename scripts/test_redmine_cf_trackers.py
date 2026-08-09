#!/usr/bin/env python3
"""Tests RM2592 — ciblage des trackers par champ personnalisé.

`redmine-config-check` exigeait chaque CF sur TOUS les trackers. Il réclamait
donc « GIT Branche » sur le tracker Assistance, où aucun ticket ne produit de
code : cinq écarts assumés signalés à chaque passage. Un contrôle qui crie en
permanence finit ignoré — et c'est là qu'il masque les vrais trous.

Lancer : python3 scripts/test_redmine_cf_trackers.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rcc", HERE / "redmine-config-check.py")
rcc = importlib.util.module_from_spec(spec)
sys.modules["rcc"] = rcc
try:
    spec.loader.exec_module(rcc)
except SystemExit:
    pass

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


LIVE = {
    "trackers": {1: {"name": "Anomalie"}, 2: {"name": "Evolution"},
                 3: {"name": "Assistance"}, 4: {"name": "Tâche"}},
    "custom_fields": {},
}
REF_TRACKERS = {"bugfix": 1, "feature": 2, "assistance": 3, "autre": 4}


def drifts_for(cf_spec, assoc_names):
    live = dict(LIVE)
    live["custom_fields"] = {9: {"name": "X", "trackers": [{"name": n} for n in assoc_names]}}
    ref = {"trackers": REF_TRACKERS, "custom_fields": {9: dict(cf_spec, name="X", type="issue")}}
    out = []
    rcc.check_cf_trackers(ref, live, out)
    return out


# — sans `trackers:` : comportement d'avant, tous les trackers exigés —
check("sans ciblage, un CF absent d'un tracker est signalé",
      len(drifts_for({}, ["Anomalie", "Evolution", "Tâche"])) == 1)
check("sans ciblage, un CF présent partout est propre",
      drifts_for({}, ["Anomalie", "Evolution", "Assistance", "Tâche"]) == [])

# — avec `trackers:` : seuls les trackers visés comptent —
cible = {"trackers": ["bugfix", "feature", "autre"]}
check("l'absence sur un tracker NON visé ne fait plus de bruit",
      drifts_for(cible, ["Anomalie", "Evolution", "Tâche"]) == [])
check("l'absence sur un tracker VISÉ reste signalée",
      len(drifts_for(cible, ["Anomalie", "Evolution"])) == 1)

d = drifts_for(cible, ["Anomalie", "Evolution"])
check("le message ne réclame que les trackers visés",
      "Assistance" not in str(d[0]) and "Tâche" in str(d[0]))

# — un CF associé à AUCUN tracker reste une alerte : Redmine l'ignorerait
#   silencieusement à l'écriture, c'est le cas le plus coûteux —
vide = drifts_for(cible, [])
check("un CF sans aucun tracker est toujours signalé", len(vide) == 1)
check("et le message dit qu'il serait ignoré à l'écriture",
      "AUCUN tracker" in str(vide[0]))

# — un ciblage qui ne correspond à rien ne doit pas inventer d'alerte —
check("un ciblage vers un tracker inconnu n'invente pas de drift",
      drifts_for({"trackers": ["inexistant"]}, ["Anomalie"]) == [])

# — la référence réelle du dépôt doit déclarer le ciblage sur les CF liés au code —
ref_yml = (HERE.parent / "redmine.reference.yml").read_text(encoding="utf-8")
for cf in ("GIT Branche", "GIT PR", "Environnement de test", "AI Test par agent"):
    ligne = next((l for l in ref_yml.splitlines() if f'"{cf}"' in l), "")
    check(f"« {cf} » déclare ses trackers", "trackers:" in ligne)
    check(f"« {cf} » exclut bien Assistance", "assistance" not in ligne.split("used_by")[0])

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests ciblage CF/trackers RM2592 passent")
