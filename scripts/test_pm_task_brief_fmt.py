#!/usr/bin/env python3
"""Tests RM2699 — formatage des durées du brief (`fmt_minutes`).

Le piège corrigé : `f"{mn/60:.0f}h{mn%60:02.0f}"` ARRONDIT la partie heures
alors que les minutes sont calculées à part (`mn % 60`). Toute durée dont les
minutes dépassent 30 gagnait une heure à l'affichage (90 min → « 2h30 »), et
l'arrondi au pair de Python faisait tomber juste un cas sur deux (150 → « 2h30 »
correct, 210 → « 4h30 » faux) — d'où un bug qui survivait à une relecture rapide.

Lancer : python3 scripts/test_pm_task_brief_fmt.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location("pm_task_brief", HERE / "pm-task-brief.py")
brief = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brief)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# Table de vérité : les minutes affichées sont TOUJOURS `mn % 60`, donc les
# heures doivent être tronquées, jamais arrondies.
CAS = [
    (0, "0min"),
    (45, "45min"),
    (59, "59min"),
    (60, "1h00"),
    (61, "1h01"),
    (90, "1h30"),        # ex-« 2h30 »
    (110, "1h50"),       # ex-« 2h50 »
    (119, "1h59"),       # ex-« 2h59 »
    (150, "2h30"),       # tombait juste par hasard (arrondi au pair)
    (210, "3h30"),       # ex-« 4h30 »
    (250, "4h10"),       # tombait juste
    (1439, "23h59"),
]
for mn, attendu in CAS:
    got = brief.fmt_minutes(mn)
    check(f"fmt_minutes({mn}) = {attendu}", got == attendu, f"obtenu {got!r}")

# Cohérence structurelle : les heures affichées ne dépassent jamais mn // 60,
# sur toute la plage — la propriété que l'arrondi violait.
bad = []
for mn in range(0, 24 * 60):
    s = brief.fmt_minutes(mn)
    if "h" not in s:
        continue
    h, m = s.split("h")
    if int(h) != mn // 60 or int(m) != mn % 60:
        bad.append((mn, s))
check("aucune heure arrondie sur 0→24 h", not bad, f"{len(bad)} écart(s), ex. {bad[:3]}")

# Entrées molles : None et float ne doivent pas faire tomber un brief.
check("None → 0min", brief.fmt_minutes(None) == "0min")
check("float toléré", brief.fmt_minutes(90.0) == "1h30", f"obtenu {brief.fmt_minutes(90.0)!r}")

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests fmt_minutes RM2699 passent")
