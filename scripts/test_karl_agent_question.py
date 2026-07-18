#!/usr/bin/env python3
"""Tests RM2329 — extraction de la question d'un pane pour la lecture vocale.

Unitaire (sans tmux ni réseau) : _extract_question (pure) + gardes d'op_question.
Lancer : python3 scripts/test_karl_agent_question.py
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


# — dialogue claude typique : bordures TUI + curseur nettoyés, aplati en phrase —
pane = """  du bruit avant
╭──────────────────────────────╮
│ Do you want to make this edit to config.py?  │
│ ❯ 1. Yes                     │
│   2. No, and tell Claude what to do differently │
╰──────────────────────────────╯"""
q = ka._extract_question(pane)
check("question extraite", q is not None and "Do you want to make this edit to config.py?" in q)
check("options du menu incluses (contexte du choix)", "1. Yes" in q and "2. No" in q)
check("décor TUI ôté", "╭" not in q and "│" not in q and "❯" not in q)
check("bruit d'avant-question exclu", "du bruit avant" not in q)

# — prompt (y/n) nu —
q = ka._extract_question("$ make deploy\nOverwrite prod.cfg? (y/n)")
check("prompt (y/n) extrait", q == "Overwrite prod.cfg? (y/n)")

# — pas de question —
check("pane sans question → None", ka._extract_question("$ tests OK\n$ ") is None)
check("pane vide → None", ka._extract_question("") is None)

# — bornage : bloc long tronqué à 500 caractères —
long_pane = "Would you like to continue?\n" + ("x" * 300 + "\n") * 4
q = ka._extract_question(long_pane)
check("texte borné à 500 caractères", q is not None and len(q) <= 500)

# — op_question : gardes 400/404 —
ka._has_session = lambda rm_id: False
try:
    ka.op_question("999999")
    check("session absente → 404", False)
except ka.ApiError as e:
    check("session absente → 404", e.code == 404)
try:
    ka.op_question("nom invalide !")
    check("sid invalide → 400", False)
except ka.ApiError as e:
    check("sid invalide → 400", e.code == 400)

# — op_question : chemin nominal avec tmux simulé —
ka._has_session = lambda rm_id: True
ka._tmux = lambda *a, timeout=10: (0, pane, "")
r = ka.op_question("42")
check("op_question renvoie la question nettoyée", "make this edit" in (r["question"] or ""))
ka._tmux = lambda *a, timeout=10: (0, "$ rien", "")
check("op_question sans question → null", ka.op_question("42")["question"] is None)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests question RM2329 passent")
