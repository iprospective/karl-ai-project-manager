#!/usr/bin/env python3
"""Tests RM2281 — pm-task-description-update : build_new_description (pur).

Couvre le bug : --set-from-file + --check dans le MÊME appel ignorait les
coches (description ET MD poussés sans les cases). Lancer :
python3 scripts/test_pm_task_description_update.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "pm_task_description_update", HERE / "pm-task-description-update.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


OLD = "## T\n\n- [ ] un\n- [ ] deux\n"
NEW = "## T2\n\n- [ ] alpha\n- [ ] beta\n- [ ] gamma\n"

# 1. LE bug : --set-from-file + --check → les coches s'appliquent au fichier
nd, total, checked, changed, bits, dchanged = mod.build_new_description(
    OLD, NEW, {1, 3}, set(), False)
check("set+check : items cochés dans la nouvelle desc",
      "- [x] alpha" in nd and "- [ ] beta" in nd and "- [x] gamma" in nd)
check("set+check : compteurs (3 items, 2 cochés)", total == 3 and checked == 2)
check("set+check : changed liste les coches", [c for c, v in changed if v] == [1, 3])
check("set+check : note remplacement + coches",
      bits[0].startswith("description remplacée") and "coché item(s) 1,3" in bits[1])
check("set+check : desc_changed", dchanged is True)

# 2. --set-from-file seul : comportement RM2578 inchangé
nd2, t2, c2, ch2, bits2, dch2 = mod.build_new_description(OLD, NEW, set(), set(), False)
check("set seul : fichier intact, rien de coché", nd2 == NEW and ch2 == [] and c2 == 0)
check("set seul : note remplacement seule", bits2 == ["description remplacée intégralement"])

# 3. fichier identique à la desc → desc_changed False
nd3, *_rest, dch3 = mod.build_new_description(OLD, OLD, set(), set(), False)
check("set identique : pas de changement", dch3 is False)

# 4. mode check pur : inchangé
nd4, t4, c4, ch4, bits4, dch4 = mod.build_new_description(OLD, None, {2}, set(), False)
check("check pur : item 2 coché", "- [x] deux" in nd4 and dch4 is True)
check("check pur : note coche", bits4 == ["coché item(s) 2"])

# 5. uncheck avec set-from-file (fichier livré pré-coché)
PRE = "- [x] a\n- [x] b\n"
nd5, t5, c5, ch5, _b5, _d5 = mod.build_new_description(OLD, PRE, set(), {2}, False)
check("set+uncheck : décoche appliquée", "- [x] a" in nd5 and "- [ ] b" in nd5 and c5 == 1)

if fails:
    print(f"\n✗ {len(fails)} échec(s)")
    raise SystemExit(1)
print("\nOK — build_new_description (RM2281)")
