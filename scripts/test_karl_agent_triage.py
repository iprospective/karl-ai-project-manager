#!/usr/bin/env python3
"""Tests RM1952 — triage ROI des tickets ouverts.

Unitaire : le classement des signaux de levier (`triage_flags`) et la forme de
`op_triage`. Le score ROI lui-même est celui de priority.py (RM1717), testé
comme réutilisation (un gain plus élevé doit scorer plus haut).

Lancer : python3 scripts/test_karl_agent_triage.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


F = ka.triage_flags
by = {10: "ferme", 11: "en_cours", 12: "a_faire"}

# — dépendances : un dépendant non ferme (ou inconnu) bloque —
r = F([10], by, 0, "a_faire")
check("dep ferme → non bloqué", r["blocked"] is False and r["blocked_by"] == [])
r = F([11], by, 0, "a_faire")
check("dep en_cours → bloqué + blocked_by", r["blocked"] is True and r["blocked_by"] == [11])
r = F([999], by, 0, "a_faire")
check("dep inconnu → bloqué (prudence)", r["blocked"] is True and r["blocked_by"] == [999])
r = F([10, 11], by, 0, "a_faire")
check("mix : seul le non-ferme bloque", r["blocked_by"] == [11])
r = F([], by, 0, "a_faire")
check("aucune dépendance → non bloqué", r["blocked"] is False)
r = F(None, by, 0, "nouveau")
check("depends_on absent toléré", r["blocked"] is False)

# — validation & débloquants —
for st in ("a_tester_dev", "a_tester_demandeur", "a_mep"):
    check(f"{st} → en validation", F([], by, 0, st)["awaiting_validation"] is True)
check("nouveau → pas en validation", F([], by, 0, "nouveau")["awaiting_validation"] is False)
check("unblocks reporté", F([], by, 5, "nouveau")["unblocks"] == 5)
check("unblocks None → 0", F([], by, None, "nouveau")["unblocks"] == 0)

# — réutilisation du scorer priority.py : un gain plus élevé score plus haut —
import priority as prio
lo = prio.task_score({"priority": "normal", "roi": {"immediate_benefit": 1},
                      "estimate": {"time_minutes": 60}}, 80.0)
hi = prio.task_score({"priority": "normal", "roi": {"immediate_benefit": 5},
                      "estimate": {"time_minutes": 60}}, 80.0)
check("plus de gain → plus de score (scorer réutilisé)", hi > lo)
urg = prio.task_score({"priority": "urgent", "roi": {"immediate_benefit": 1},
                       "estimate": {"time_minutes": 60}}, 80.0)
check("priorité urgente pèse plus que normale", urg > lo)

# — op_triage : forme exploitable (l'ordre/scores sont couverts en live) —
rep = ka.op_triage({})
check("op_triage rend rate_eur/count/tickets",
      set(["rate_eur", "count", "tickets"]) <= set(rep.keys()))
check("tickets est une liste", isinstance(rep["tickets"], list))
check("count cohérent avec la liste", rep["count"] == len(rep["tickets"]))
# tri décroissant par score si des tickets existent
scores = [t["score"] for t in rep["tickets"]]
check("classement décroissant par score", scores == sorted(scores, reverse=True))
if rep["tickets"]:
    t0 = rep["tickets"][0]
    check("chaque ticket porte les champs de triage",
          set(["rm_id", "score", "status", "priority", "unblocks", "blocked",
               "awaiting_validation"]) <= set(t0.keys()))

if fails:
    print(f"\n{len(fails)} test(s) en échec : {fails}")
    sys.exit(1)
print("\nOK — tous les tests triage passent")
