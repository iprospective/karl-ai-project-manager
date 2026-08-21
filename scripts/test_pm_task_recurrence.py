#!/usr/bin/env python3
"""Tests RM2772 — périodicité d'un ticket récurrent (CF Redmine 7 « Recurrence »).

Deux pièges couverts ici :
  * Redmine rend le **label** de l'énumération dans `custom_fields[].value`
    ("Mensuelle"), pas le value id — un mapping indexé par id seul ne reconnaîtrait
    jamais la valeur relue, et `pm-task-recurrence set` conclurait à tort que
    Redmine a ignoré l'écriture ;
  * une périodicité **vidée** côté Redmine doit repasser le frontmatter à `None`,
    sinon un ticket cesse d'être récurrent sans que le MD le sache.

Lancer : python3 scripts/test_pm_task_recurrence.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import redmine_utils  # noqa: E402

spec = importlib.util.spec_from_file_location("pts", HERE / "pm-task-sync.py")
pts = importlib.util.module_from_spec(spec)
sys.modules["pts"] = pts
try:
    spec.loader.exec_module(pts)
except SystemExit:
    pass

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# ── référence ────────────────────────────────────────────────────────────
cf_id, values = redmine_utils.recurrence_cf()
check("recurrence_cf() rend l'id du CF", cf_id == 7)
check("recurrence_cf() rend les 4 périodicités",
      set(values) == {"quotidienne", "hebdomadaire", "mensuelle", "annuelle"})

# ── label ou value id, casse indifférente ────────────────────────────────
check("label Redmine reconnu", redmine_utils.recurrence_from_cf("Mensuelle") == "mensuelle")
check("label bas-de-casse reconnu", redmine_utils.recurrence_from_cf("mensuelle") == "mensuelle")
check("value id reconnu", redmine_utils.recurrence_from_cf("8") == "mensuelle")
check("value id entier reconnu", redmine_utils.recurrence_from_cf(9) == "annuelle")
check("valeur vide → None", redmine_utils.recurrence_from_cf("") is None)
check("None → None", redmine_utils.recurrence_from_cf(None) is None)
check("liste vide (CF multi non renseigné) → None", redmine_utils.recurrence_from_cf([]) is None)
check("valeur inconnue → None", redmine_utils.recurrence_from_cf("Bimestrielle") is None)


# ── rapatriement Redmine → frontmatter ───────────────────────────────────
def issue(cf_value):
    """Issue Redmine minimale portant (ou non) le CF Recurrence."""
    return {"subject": "t", "status": {"id": 2}, "priority": {"id": 2},
            "custom_fields": ([{"id": 7, "value": cf_value}]
                              if cf_value is not None else [])}


d = pts.diff_fields({"recurrence": None}, issue("Mensuelle"))
check("CF posé → diff vers mensuelle", d.get("recurrence") == (None, "mensuelle"))

d = pts.diff_fields({"recurrence": "mensuelle"}, issue("Mensuelle"))
check("CF inchangé → pas de diff", "recurrence" not in d)

d = pts.diff_fields({"recurrence": "mensuelle"}, issue(""))
check("CF vidé → retour à None", d.get("recurrence") == ("mensuelle", None))

d = pts.diff_fields({}, issue(None))
check("ni MD ni CF → pas de diff (fiche antérieure au champ)", "recurrence" not in d)

d = pts.diff_fields({"recurrence": "mensuelle"}, issue("Annuelle"))
check("périodicité changée → diff", d.get("recurrence") == ("mensuelle", "annuelle"))

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
