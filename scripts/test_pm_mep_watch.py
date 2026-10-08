#!/usr/bin/env python3
"""Tests RM3278 — la file « à vérifier en prod » se rappelle à nous.

Ce que ces tests protègent :

  · l'attente se compte depuis l'entrée dans le STATUT, pas depuis `updated` — une note ou un
    tick de conso rafraîchit `updated` et ferait passer pour jeune un ticket qui attend depuis
    deux mois (RM2381 : 71 jours) ;
  · **on ne notifie jamais sans preuve** que le code est en prod : un ticket dont la MEP n'a
    pas eu lieu est un autre problème, et le supposer déployé serait un mensonge ;
  · le message DIT de quelle preuve il s'agit — filiation depuis le checkout de prod, ou
    simple merge dans la branche que la prod suit (le pull côté serveur n'est pas vérifiable
    sans SSH) ;
  · un worktree de session n'est jamais pris pour le checkout de prod : il disparaît à la
    livraison, et on conclurait « en prod » sur du code qui n'y est pas.

Lancer : python3 scripts/test_pm_mep_watch.py
"""
import importlib.util
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("_mw", HERE / "pm-mep-watch.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

fails = []


def chk(label, cond):
    print(("✓ " if cond else "✗ ") + label)
    if not cond:
        fails.append(label)


AUJ = date(2026, 9, 30)

# ── l'âge se lit dans status_history ──────────────────────────────────────────
FM = {"status": "en_mep", "updated": "2026-09-29T10:00",
      "status_history": [{"status": "a_mep", "at": "2026-09-01T09:00"},
                         {"status": "en_mep", "at": "2026-09-06T09:00"}]}
chk("l'attente part de l'entrée dans le statut (24 j), pas de `updated` (1 j)",
    W.jours_attente(FM, AUJ) == 24)
chk("plusieurs passages : c'est le DERNIER qui compte",
    W.jours_attente({"status": "en_mep", "status_history": [
        {"status": "en_mep", "at": "2026-01-01T09:00"},
        {"status": "a_corriger", "at": "2026-09-20T09:00"},
        {"status": "en_mep", "at": "2026-09-28T09:00"}]}, AUJ) == 2)
chk("sans historique : repli sur `updated`",
    W.jours_attente({"status": "en_mep", "updated": "2026-09-25T08:00"}, AUJ) == 5)
chk("rien de datable → None", W.jours_attente({"status": "en_mep"}, AUJ) is None)
chk("une date future ne rend pas un âge négatif",
    W.jours_attente({"status": "en_mep", "updated": "2026-12-01T08:00"}, AUJ) == 0)

# ── ce qui se notifie, et ce qui se taît ──────────────────────────────────────
niv, msg = W.verdict("en_mep", "checkout", 24)
chk("en_mep + preuve + au-delà du seuil → warn", niv == "warn" and "24 jours" in msg)
chk("le message dit quoi faire (colonne Prod du protocole, puis fermer)",
    "Prod" in msg and "fermer" in msg)
chk("le message dit de quelle preuve il s'agit", "filiation des commits" in msg)
niv, msg = W.verdict("en_mep", "branche 19.0-mmi", 71)
chk("preuve par la branche : le message ne prétend pas que le serveur a tiré",
    niv == "warn" and "pull côté serveur n'est pas vérifié" in msg)
chk("en dessous du seuil : rien", W.verdict("en_mep", "checkout", 2)[0] is None)
chk("pas de preuve : rien, quel que soit l'âge",
    W.verdict("en_mep", None, 300)[0] is None)
chk("… et le motif le dit", "non prouvable" in W.verdict("en_mep", None, 300)[1])
niv, msg = W.verdict("a_mep", "checkout", 13)
chk("a_mep + code déjà en prod → info : le statut est en retard",
    niv == "info" and "statut en retard" in msg)
chk("a_mep sans preuve : rien (la MEP n'a simplement pas eu lieu)",
    W.verdict("a_mep", None, 50)[0] is None)
chk("a_mep + preuve notifie sans attendre le seuil (l'incohérence est immédiate)",
    W.verdict("a_mep", "checkout", 0)[0] == "info")
chk("attente indatable + en_mep : rien", W.verdict("en_mep", "checkout", None)[0] is None)
chk("un statut hors file n'est jamais considéré", W.verdict("en_cours", "checkout", 99)[0] is None)
chk("le seuil est réglable", W.verdict("en_mep", "checkout", 5, seuil=7)[0] is None
    and W.verdict("en_mep", "checkout", 8, seuil=7)[0] == "warn")

# ── le checkout de prod ne se devine pas ──────────────────────────────────────
class _Cfg:
    def __init__(self, racine):
        self.projects_root = racine


import os  # noqa: E402

anc = os.environ.pop("PM_CORE_DIR", None)
try:
    chk("aucune racine de projets → pas de checkout de prod supposé",
        W.checkout_prod_pm(_Cfg(None)) is None)
    faux = HERE.parent / "var" / "faux-core" / "envs" / "ai-project-management-rm1"
    chk("un worktree de session n'est jamais pris pour la prod",
        W.checkout_prod_pm(_Cfg(faux / "projects")) is None)
finally:
    if anc is not None:
        os.environ["PM_CORE_DIR"] = anc

src = (HERE / "pm-mep-watch.py").read_text(encoding="utf-8")
chk("rapport par défaut : --apply commande l'écriture",
    '"--apply"' in src and "if not args.apply:" in src)
chk("les notifications passent par pm_notify (clé stable = pas de doublon)",
    "pm_notify.add(" in src and "job=JOB" in src)
chk("une entrée dont le ticket a bougé est marquée traitée",
    'pm_notify.mark(resolues, "traite")' in src)
chk("aucun chemin de prod codé en dur", "/zfs/workspaces" not in src)

# ── câblage de l'ordonnanceur ─────────────────────────────────────────────────
reg = (HERE.parent / "jobs.reference.yml").read_text(encoding="utf-8")
chk("le job est déclaré au registre de l'ordonnanceur (pas un cron à part)",
    "mep-watch:" in reg and "pm-mep-watch.py" in reg)
chk("le job s'exécute avec --apply", "--apply" in reg.split("mep-watch:", 1)[1][:400])

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — file « à vérifier en prod » : âge, preuve, notification (RM3278)")
