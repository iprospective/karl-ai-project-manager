#!/usr/bin/env python3
"""Tests RM2828 — reprise en lot des étiquettes (frontmatter `tags` → CF Redmine).

Ce que ces tests protègent :

  · la reprise est **additive** — une valeur posée dans l'UI Redmine et inconnue ici
    n'est JAMAIS retirée (c'est l'incident RM2840, mais à l'échelle du parc : 292
    tickets écrits d'un coup) ;
  · une valeur hors vocabulaire n'est pas poussée et n'est pas perdue non plus : elle
    reste au frontmatter, et elle est COMPTÉE, avec la raison ;
  · une valeur décidée mais pas encore créée dans Redmine n'a pas d'id : la pousser
    ferait échouer le PUT entier (`cf_payload` l'écarte) — elle est traitée comme locale ;
  · ce que Redmine porte en plus redescend au frontmatter : la parité va dans les deux sens.

Lancer : python3 scripts/test_pm_tags_backfill.py
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_tags

_spec = importlib.util.spec_from_file_location("_bf", HERE / "pm-tags-backfill.py")
BF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BF)

fails = []


def chk(label, cond):
    print(("✓ " if cond else "✗ ") + label)
    if not cond:
        fails.append(label)


VOCAB = set(pm_tags.vocabulary())
A, B = "front", "git"                      # deux valeurs du vocabulaire réel
chk("le vocabulaire de référence est chargé", {A, B} <= VOCAB)

# — cas nominal : le local connu monte, le distant est préservé —
p = BF.plan_tags([A, "cockpit"], [B])
chk("la valeur connue est à pousser", p["a_pousser"] == [A])
chk("le CF voulu est l'UNION (le distant n'est jamais retiré)", p["cf"] == sorted([A, B]))
chk("ce que Redmine portait en plus redescend au frontmatter", p["a_rapatrier"] == [B] and B in p["frontmatter"])
chk("le mot-clé local reste au frontmatter et est compté", "cockpit" in p["frontmatter"] and p["locales"] == ["cockpit"])

# — rien à faire —
p = BF.plan_tags([A], [A])
chk("déjà conforme : rien à pousser ni à rapatrier", not p["a_pousser"] and not p["a_rapatrier"])
p = BF.plan_tags(["cockpit", "karl"], [])
chk("que des mots-clés locaux : aucun push, CF voulu vide", not p["a_pousser"] and p["cf"] == [])
p = BF.plan_tags([], [A])
chk("fiche sans étiquette mais CF rempli : on rapatrie, on ne vide pas", p["cf"] == [A] and p["a_rapatrier"] == [A])

# — lecture distante impossible : on ne conclut pas —
p = BF.plan_tags([A], None)
chk("CF illisible : aucun push proposé (on ne devine pas l'état distant)",
    p["cf"] is None and p["a_pousser"] == [])

# — valeur du vocabulaire pas encore créée dans Redmine —
reel = pm_tags.pending_values
pm_tags.pending_values = lambda: [A]
try:
    p = BF.plan_tags([A, B], [])
    chk("valeur en attente de création : pas poussée (sinon PUT 422), comptée comme locale",
        p["a_pousser"] == [B] and A in p["locales"])
finally:
    pm_tags.pending_values = reel

# — normalisation : casse et doublons ne créent pas de faux écart —
p = BF.plan_tags([A.upper(), A], [A])
chk("casse et doublons ne produisent pas de push fantôme", not p["a_pousser"])

# — le PUT réutilisé est celui du geste unitaire, pas un second —
src = (HERE / "pm-tags-backfill.py").read_text(encoding="utf-8")
chk("le PUT est celui de pm-task-tag (un seul chemin d'écriture)",
    "_TAG.push_cf(" in src and "pm-task-tag.py" in src)
chk("dry-run par défaut : --go commande l'écriture", '"--go"' in src and "if not args.go:" in src)
chk("dump JSONL avant écriture (leçon RM2409)", "tags-backfill-" in src and "dump.open" in src)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — reprise en lot des étiquettes : additive, vocabulaire respecté (RM2828)")
