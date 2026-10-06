#!/usr/bin/env python3
"""Tests RM2940 — un primaire Redmine que l'outillage d'écriture ne sert pas doit être REFUSÉ, pas écrit.

Les scripts qui écrivent l'état d'un ticket visent l'instance par défaut, avec les ids de
`redmine.reference.yml`, sans regarder le primaire déclaré par le projet. Pour un Redmine
tiers en primaire, le résultat serait un PUT vers le mauvais serveur ou avec des ids d'un
autre Redmine — HTTP 204, aucun effet, aucun message. La garde en fait un refus lisible.

Aucun projet n'est dans ce cas aujourd'hui : ces tests fabriquent le cas.

Lancer : python3 scripts/test_pm_primary_guard.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import redmine_utils as R
from pm_registry import Instance

fails = []


def chk(label, cond):
    print(("✓ " if cond else "✗ ") + label)
    if not cond:
        fails.append(label)


REF = "https://tasks.iprospective.fr"
ipro = Instance(name="redmine-ipro", axis="task", type="redmine", url=REF)
matnat = Instance(name="redmine-matnat", axis="task", type="redmine", url="https://tasks.materiaux-naturels.fr")
autre = Instance(name="jira-x", axis="task", type="jira", url="https://x.atlassian.net")

chk("l'instance de la référence est servie : aucun refus", R.primary_write_problem(ipro, REF) is None)
chk("… même avec un « / » final d'un côté", R.primary_write_problem(ipro, REF + "/") is None)
why = R.primary_write_problem(matnat, REF)
chk("un Redmine tiers en primaire est refusé", bool(why))
chk("… et le motif nomme l'instance, les deux serveurs et le no-op silencieux",
    why and "redmine-matnat" in why and REF in why and "materiaux-naturels" in why and "silencieux" in why)
chk("un primaire qui n'est pas un Redmine est refusé", bool(R.primary_write_problem(autre, REF)))
chk("pas d'instance résolue : rien à dire", R.primary_write_problem(None, REF) is None)
chk("référence sans URL : on ne refuse pas à l'aveugle", R.primary_write_problem(matnat, "") is None)
chk("la vraie référence est bindée sur ipro", R.reference_instance_url() == REF)

import pm_scope
chk("fiche hors de tout projet : la garde se tait (jamais de plantage)",
    pm_scope.primary_write_refusal(Path("/tmp/nulle-part/RM1_x.md")) is None)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — garde du primaire non servi (RM2940)")
