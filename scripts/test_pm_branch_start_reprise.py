#!/usr/bin/env python3
"""Tests RM3152 — la branche d'un ticket se REPREND, elle ne se recompose pas.

Le nom était recalculé à chaque prise depuis le nom de fichier, tronqué à `SLUG_MAX` (40). Un ticket
dont le slug dépassait cette longueur se voyait donc attribuer un NOUVEAU nom, donc une SECONDE
branche : tout partait dessus pendant que la MR ouverte continuait de regarder la première. Elle
restait « non mergeable », et le ticket ne partait jamais en production — **sans que rien ne dise
qu'il y avait deux branches**. RM3059 est resté dans cet état plusieurs jours, exclu de chaque
passage de mise en prod, avec pour seul diagnostic « MR en conflit » : exact, et sans rapport.

Ce que ces tests tiennent :
  - un ticket déjà branché garde sa branche, quelle que soit la longueur de son slug ;
  - une divergence entre le nom recomposé et la branche réelle est DITE, jamais résolue en silence ;
  - plusieurs branches pour un ticket sont signalées, et la plus complète l'emporte ;
  - `--slug` explicite reste souverain — c'est le geste qui répare.

Lancer : python3 scripts/test_pm_branch_start_reprise.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core                       # noqa: E402
hermetic_core()

spec = importlib.util.spec_from_file_location("pbs", HERE / "pm-branch-start.py")
pbs = importlib.util.module_from_spec(spec); sys.modules["pbs"] = pbs
try:
    spec.loader.exec_module(pbs)
except SystemExit:
    pass

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


R = pbs.reprendre_branche
LONG = "3059-wiki-sync-references-doc-partagee-sans-lien-backti"
COURT = "3059-wiki-sync-references-doc-partagee-sans-l"

# ── le cas qui a coûté des jours ────────────────────────────────────────────
b, note = R(COURT, LONG, {LONG}, 3059)
check("la branche de la fiche est reprise, même si le nom recomposé est plus court", b == LONG, b)
check("…et la divergence est DITE : c'est ce que personne ne voyait", "REPRISE" in note and COURT in note, note)

b, note = R(COURT, "", {LONG}, 3059)
check("sans rien dans la fiche, la branche du dépôt est reprise", b == LONG, b)
check("…et dite aussi", "REPRISE" in note, note)

# ── un ticket neuf n'est pas gêné ───────────────────────────────────────────
b, note = R("3200-neuf", "", set(), 3200)
check("ticket sans branche : le nom composé est retenu, sans bruit", b == "3200-neuf" and note == "", note)
b, note = R("3200-neuf", "3200-neuf", {"3200-neuf"}, 3200)
check("fiche et nom composé identiques : rien à signaler", b == "3200-neuf" and note == "", note)

# ── état anormal : plusieurs branches ───────────────────────────────────────
b, note = R(COURT, "", {LONG, COURT}, 3059)
check("plusieurs branches : la plus complète l'emporte (une troncature ne fait que raccourcir)", b == LONG, b)
check("…et l'anomalie est signalée, avec la liste et quoi faire",
      "⚠" in note and "2 branches" in note and "À nettoyer" in note, note)
b, note = R(COURT, LONG, {LONG, COURT}, 3059)
check("la fiche tranche quand elle parle, mais l'autre branche est quand même signalée",
      b == LONG and "aussi 1 autre" in note, note)

# ── ce qui ne doit PAS être repris ──────────────────────────────────────────
b, _ = R("3200-neuf", "2999-autre-ticket", {"2999-autre-ticket"}, 3200)
check("une branche d'un AUTRE ticket n'est jamais reprise", b == "3200-neuf", b)
b, _ = R("3200-neuf", "", {"32000-piege"}, 3200)
check("un préfixe qui ressemble (32000-) n'est pas confondu avec 3200-", b == "3200-neuf", b)

# ── `--slug` reste souverain : c'est le geste qui répare ────────────────────
src = (HERE / "pm-branch-start.py").read_text(encoding="utf-8")
check("`--slug` explicite court-circuite la reprise (c'est ainsi qu'on répare une divergence)",
      "if not args.slug:" in src.split("branch = f\"{args.rm_id}-{slug}\"")[1][:400], "garde absente")
check("la divergence passe par `warn`, pas `info` — `info` est muet en sortie dense, donc invisible",
      "out.warn(note)" in src and "out.info(\"• \" + note)" not in src)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — la branche d'un ticket se reprend (RM3152)")
