#!/usr/bin/env python3
"""Tests RM3255 — le capteur de marge compare chaque rôle à SON plafond.

Un rôle dont le plafond a été relevé par arbitrage (RM3238 : worker-infra à 30 000) dépassait le
plafond PAR DÉFAUT (29 000) sans dépasser le sien. Le capteur criait « DÉPASSE » en niveau critique,
alors que l'invariant réel (`--check`) passait. Une alerte fausse coûte plus que son bruit : elle
apprend à ignorer celle qui sera vraie.

Lancer : python3 scripts/test_pm_context_budget_notify.py
"""
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stdout

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pcb", HERE / "pm-context-budget.py")
B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def essai(mesures: dict, budgets: dict):
    """Lance `notifie` sur des mesures et des plafonds factices ; rend (sortie, notifications)."""
    B.ROLES = list(mesures)
    B.load_budget = lambda: budgets
    B.components = lambda r, **k: [("x", "x", mesures[r])]
    with tempfile.TemporaryDirectory() as d:
        os.environ["PM_NOTIFY_DIR"] = d
        sys.modules.pop("pm_notify", None)
        buf = io.StringIO()
        with redirect_stdout(buf):
            B.notifie()
        f = pathlib.Path(d) / "notifications.jsonl"
        notes = [json.loads(l) for l in f.read_text().splitlines()] if f.is_file() else []
    return buf.getvalue(), notes


print("[RM3255] un plafond relevé par arbitrage n'est pas un dépassement")
out, notes = essai({"worker-dev": 20000, "worker-infra": 29518},
                   {"default": 29000, "worker-infra": 30000})
check("au-dessus du défaut mais sous SON plafond : pas « DÉPASSE »", "DÉPASSE" not in out, out)
check("…c'est une marge entamée, dite comme telle", "entamé sa marge" in out, out)
check("…mesurée contre le plafond du rôle (30 000), pas le défaut", "30,000" in out, out)
check("…et la notification est un avertissement, pas une alerte critique",
      notes and notes[0]["level"] == "warn", str(notes))

print("\n[RM3255] un vrai dépassement reste critique")
out, notes = essai({"worker-infra": 31000}, {"default": 29000, "worker-infra": 30000})
check("au-dessus de SON plafond : « DÉPASSE »", "DÉPASSE" in out, out)
check("…en niveau critique", notes and notes[0]["level"] == "critical", str(notes))

print("\n[RM3255] le pire rôle est celui qui est le plus près de SON plafond, pas le plus gros")
out, _ = essai({"worker-dev": 29500, "reviewer": 20000},
               {"default": 29000, "worker-dev": 40000, "reviewer": 21000})
check("reviewer (95 % de 21 000) passe devant worker-dev (74 % de 40 000)",
      "reviewer" in out, out)

print("\n[RM3255] une marge saine ne dit rien au fil")
out, notes = essai({"worker-dev": 10000}, {"default": 29000})
check("rien n'est notifié", notes == [] and "saine" in out, out)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — capteur de marge par rôle (RM3255)"))
sys.exit(1 if FAIL else 0)
