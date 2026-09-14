#!/usr/bin/env python3
"""Tests RM3155 — révision de l'estimation d'un ticket.

Ce que ces tests protègent :

  * **on ne journalise que ce qui change.** Reposer la même valeur ne doit produire
    aucune entrée : un journal qui consigne des non-événements cesse d'être lu, et
    c'est précisément dans ce journal qu'on va comparer l'estimation de création à
    celle d'après étude ;
  * **`time_minutes` ne diverge pas** de ses deux composantes. Ce champ legacy, laissé
    libre, donnerait deux chiffres sans moyen de savoir lequel ment ;
  * **`estimated_by` / `estimated_at` marquent la RÉVISION.** Sans eux, on ne sait plus
    si l'on lit un chiffrage d'étude ou le nombre jeté à la création — sur RM3107,
    l'écart était de 60 min à 930 ;
  * **le verrou et la relecture sont bien là.** L'outil existe justement pour ne plus
    refaire ce protocole à la main.

Lancer : python3 scripts/test_pm_task_estimate.py
"""
import importlib.util
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("est", HERE / "pm-task-estimate.py")
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)

NOW = "2026-09-14T06:00"
BASE = {"difficulty": "low", "human_time_minutes": 30, "ai_time_minutes": 30,
        "time_minutes": 60, "confidence": 0.5,
        "estimated_by": "pm-task-add", "estimated_at": "2026-09-01T10:00"}

# — une révision réelle —
new, diffs = E.apply_estimate(BASE, {"ai_minutes": 810, "human_minutes": 120,
                                     "difficulty": "high"}, by="claude-opus-5", now=NOW)
check("les trois champs sont appliqués",
      new["ai_time_minutes"] == 810 and new["human_time_minutes"] == 120 and new["difficulty"] == "high")
check("time_minutes est RECALCULÉ, il ne diverge pas", new["time_minutes"] == 930)
check("le total figure dans les diffs", any(l == "total (min)" for l, _, _ in diffs))
check("estimated_by marque la révision", new["estimated_by"] == "claude-opus-5")
check("estimated_at marque la révision", new["estimated_at"] == NOW)
check("l'avant est conservé dans les diffs", ("temps IA (min)", 30, 810) in diffs)
check("ce qui n'a pas changé n'est pas dans les diffs",
      not any(l == "confiance" for l, _, _ in diffs))

# — reposer la même valeur ne produit RIEN —
same, d2 = E.apply_estimate(BASE, {"difficulty": "low"}, by="x", now=NOW)
check("même valeur → aucun diff", d2 == [])
check("même valeur → estimated_by INCHANGÉ (pas de fausse révision)",
      same["estimated_by"] == "pm-task-add")

# — un champ absent au départ —
vide, d3 = E.apply_estimate({}, {"tokens": 60000}, by="x", now=NOW)
check("un champ absent se remplit", vide["tokens"] == 60000)
check("l'absence est notée « — » côté avant", ("tokens", None, 60000) in d3)

# — aucun changement demandé —
_n, d4 = E.apply_estimate(BASE, {k: None for k in E.CHAMPS}, by="x", now=NOW)
check("aucun changement demandé → aucun diff", d4 == [])

# — l'affichage DIT les champs vides —
lignes = "\n".join(E.format_estimate({"difficulty": "high"}))
check("un champ vide est affiché « — », pas masqué", "—" in lignes and "high" in lignes)
check("l'affichage couvre tous les champs révisables",
      all(lib in lignes for _f, (_c, lib, _x) in E.CHAMPS.items()))

# — le journal porte l'avant ET l'après —
entry = E.log_entry(3107, [("temps IA (min)", 30, 810)], "après étude", "claude-opus-5", NOW)
check("le journal montre la transition", "30 → 810" in entry)
check("le journal nomme qui a révisé", "claude-opus-5" in entry)
check("le motif est tracé", "après étude" in entry)
check("le journal respecte l'en-tête NORMS", entry.lstrip().startswith("## " + NOW))

# — le protocole d'écriture est bien celui du système —
src = (HERE / "pm-task-estimate.py").read_text(encoding="utf-8")
check("verrou par ticket pris", "ticket_lock(" in src)
check("relecture du frontmatter SOUS le verrou", src.index("ticket_lock(") < src.index("read_task(args.rm_id)"))
check("l'écriture passe par write_task_fm (qui pose `updated`)", "write_task_fm(" in src)
check("la poussée Redmine réutilise pm-task-metrics-push, sans remapper les CF",
      "do_estimate(" in src and "cf_id_by_name" not in src)
check("le coût n'est JAMAIS dérivé des tokens", "cost_usd" in src and "tokens *" not in src)

# — garde-fous de la ligne de commande —
def run(*args):
    return subprocess.run([sys.executable, str(HERE / "pm-task-estimate.py"), *args],
                          capture_output=True, text=True)

r = run("3155", "--confidence", "1.5")
check("--confidence hors [0,1] est refusé", r.returncode != 0 and "0.0" in (r.stdout + r.stderr))
r = run("3155", "--ai-minutes", "-5")
check("une durée négative est refusée", r.returncode != 0)
r = run("3155", "--difficulty", "enorme")
check("une difficulté hors énumération est refusée", r.returncode != 0)

print(("ÉCHEC : " + "; ".join(fails)) if fails else "OK — révision d'estimation")
sys.exit(1 if fails else 0)
