#!/usr/bin/env python3
"""Tests RM2772 — cycle de vie d'un ticket récurrent.

Deux pièges couverts ici :
  * Redmine rend le **label** de l'énumération dans `custom_fields[].value`
    ("Mensuelle"), pas le value id — un mapping indexé par id seul ne reconnaîtrait
    jamais la valeur relue, et `pm-task-recurrence set` conclurait à tort que
    Redmine a ignoré l'écriture ;
  * une périodicité **vidée** côté Redmine doit repasser le frontmatter à `None`,
    sinon un ticket cesse d'être récurrent sans que le MD le sache.

Le lot 2 ajoute le calcul CALENDAIRE de l'échéance et la sélection des échus. Les
deux pièges qui comptent ici :
  * un delta en jours ferait dériver une vérification mensuelle (5 jours d'avance
    par an) — d'où `add_months` et son rabot de fin de mois ;
  * `wake` doit être IDEMPOTENT : un ticket déjà réveillé garde une échéance dans
    le passé, et serait re-réveillé à chaque passage du cron si le statut de repos
    ne faisait pas partie des conditions.

Lancer : python3 scripts/test_pm_task_recurrence.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import redmine_utils  # noqa: E402

def _load(mod, filename):
    spec = importlib.util.spec_from_file_location(mod, HERE / filename)
    m = importlib.util.module_from_spec(spec)
    sys.modules[mod] = m
    try:
        spec.loader.exec_module(m)
    except SystemExit:
        pass
    return m


pts = _load("pts", "pm-task-sync.py")
ptr = _load("ptr", "pm-task-recurrence.py")
pdu = _load("pdu", "pm-task-description-update.py")

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


# ── lot 2 : échéance calendaire ──────────────────────────────────────────
from datetime import date  # noqa: E402

check("quotidienne = +1 jour", ptr.next_due(date(2026, 8, 21), "quotidienne") == date(2026, 8, 22))
check("hebdomadaire = +7 jours", ptr.next_due(date(2026, 8, 21), "hebdomadaire") == date(2026, 8, 28))
check("mensuelle garde le quantième",
      ptr.next_due(date(2026, 8, 21), "mensuelle") == date(2026, 9, 21))
check("mensuelle franchit l'année",
      ptr.next_due(date(2026, 12, 15), "mensuelle") == date(2027, 1, 15))
check("mensuelle rabote le 31 sur février",
      ptr.next_due(date(2026, 1, 31), "mensuelle") == date(2026, 2, 28))
check("mensuelle rabote le 31 sur un février bissextile",
      ptr.next_due(date(2024, 1, 31), "mensuelle") == date(2024, 2, 29))
check("mensuelle rabote le 31 sur un mois de 30",
      ptr.next_due(date(2026, 8, 31), "mensuelle") == date(2026, 9, 30))
check("annuelle garde la date", ptr.next_due(date(2026, 8, 21), "annuelle") == date(2027, 8, 21))
check("annuelle rabote le 29 février",
      ptr.next_due(date(2024, 2, 29), "annuelle") == date(2025, 2, 28))

# Un delta fixe de 30 jours dériverait ; le calendaire, non.
douze = date(2026, 1, 21)
for _ in range(12):
    douze = ptr.next_due(douze, "mensuelle")
check("12 passages mensuels = même quantième un an plus tard", douze == date(2027, 1, 21))

try:
    ptr.next_due(date(2026, 8, 21), "bimestrielle")
    check("périodicité inconnue → ValueError", False)
except ValueError:
    check("périodicité inconnue → ValueError", True)


# ── lot 2 : sélection des échus (wake) ───────────────────────────────────
REPOS = ptr.recurrence_resting_status()
ON = date(2026, 9, 4)


def task(**kw):
    fm = {"recurrence": "mensuelle", "status": REPOS, "due": "2026-09-01"}
    fm.update(kw)
    return fm


check("échéance passée + au repos → dû", ptr.is_due(task(), ON) is True)
check("échéance du jour → dû", ptr.is_due(task(due="2026-09-04"), ON) is True)
check("échéance future → pas dû", ptr.is_due(task(due="2026-10-01"), ON) is False)
check("ticket non récurrent → jamais dû", ptr.is_due(task(recurrence=None), ON) is False)
check("sans échéance → pas dû (rien à comparer)", ptr.is_due(task(due=None), ON) is False)
check("déjà réveillé (a_faire) → pas re-réveillé",
      ptr.is_due(task(status="a_faire"), ON) is False)
check("en cours de traitement → pas re-réveillé",
      ptr.is_due(task(status="en_cours"), ON) is False)
check("fermé → pas réveillé (récurrent retiré du service)",
      ptr.is_due(task(status="ferme"), ON) is False)
check("échéance illisible → pas dû plutôt que crash",
      ptr.is_due(task(due="bientôt"), ON) is False)


# ── lot 2 : remise à zéro de la checklist au réveil ──────────────────────
CHECKLIST = "- [x] version applicative à jour\n- [x] paquets OS à jour\n- [ ] pas de reboot\n"
txt, total, checked, changed = pdu.apply_checks(CHECKLIST, set(), set(), False, uncheck_all=True)
check("--uncheck-all décoche tout", "[x]" not in txt)
check("--uncheck-all compte les items", (total, checked) == (3, 0))
check("--uncheck-all ne signale que les items réellement changés", len(changed) == 2)
check("--uncheck-all sur une liste déjà vierge ne change rien",
      pdu.apply_checks(txt, set(), set(), False, uncheck_all=True)[3] == [])

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
