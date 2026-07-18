#!/usr/bin/env python3
"""Tests RM2302 — répondre « Oui » à une session qui pose une question.

Unitaire (sans tmux ni réseau) : _approve_answer (décision pure) et op_approve
(garde 409, séquence send-keys, journal answers.jsonl).
Lancer : python3 scripts/test_karl_agent_approve.py
"""
import importlib.util
import json
import pathlib
import sys
import tempfile

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


# — _approve_answer : décision pure sur le tail du pane —
menu = "Do you want to make this edit?\n❯ 1. Yes\n  2. No"
check("menu numéroté claude → « 1 »", ka._approve_answer(menu) == "1")
check("variante « │ 1. Yes » → « 1 »",
      ka._approve_answer("│ 1. Yes\n│ 2. No") == "1")
check("prompt texte (y/n) → « y »",
      ka._approve_answer("Overwrite file? (y/n)") == "y")
check("question sans forme de réponse → « y » (Enter validera le défaut)",
      ka._approve_answer("Would you like to continue?") == "y")
check("pas de question → None", ka._approve_answer("$ build ok\n$ ") is None)
check("menu à choix multiple (≠ oui/non) → None (RM2327 : pas de choix à l'aveugle)",
      ka._approve_answer("Quel plan ?\n❯ 1. Conservateur\n  2. Agressif") is None)
check("option 1 = Oui (fr) → « 1 »", ka._approve_answer("❯ 1. Oui\n  2. Non") == "1")
check("le menu prime sur (y/n) dans le même tail",
      ka._approve_answer("proceed? (y/n)\n❯ 1. Yes") == "1")

# — op_approve : gardes + séquence de touches —
calls = []


def fake_tmux(*args, timeout=10):
    calls.append(args)
    if args[0] == "capture-pane":
        return 0, fake_tmux.pane, ""
    return 0, "", ""


ka._tmux = fake_tmux
ka._has_session = lambda rm_id: True
ka.ANSWERS_LOG = pathlib.Path(tempfile.mkdtemp()) / "answers.jsonl"

# menu numéroté : « 1 » seul, PAS d'Enter (la touche chiffre valide seule)
fake_tmux.pane = menu
r = ka.op_approve({"rm_id": "42"})
sent = [c for c in calls if c[0] == "send-keys"]
check("menu : réponse « 1 » envoyée", r["sent"] == "1" and ("-l", "--", "1") == sent[0][-3:])
check("menu : pas d'Enter derrière", all("Enter" not in c for c in sent))

# prompt y/n : « y » PUIS Enter
calls.clear()
fake_tmux.pane = "Overwrite? (y/n)"
r = ka.op_approve({"rm_id": "42"})
sent = [c for c in calls if c[0] == "send-keys"]
check("y/n : « y » puis Enter", r["sent"] == "y" and len(sent) == 2 and sent[1][-1] == "Enter")

# journal answers.jsonl (socle RM2305)
lines = [json.loads(ln) for ln in ka.ANSWERS_LOG.read_text().splitlines()]
check("journal : une entrée par réponse (rm_id, sent, question)",
      len(lines) == 2 and lines[1]["rm_id"] == "42" and lines[1]["sent"] == "y"
      and "(y/n)" in lines[1]["question"])

# pas de question → 409, rien envoyé
calls.clear()
fake_tmux.pane = "$ tail du shell au repos"
try:
    ka.op_approve({"rm_id": "42"})
    check("pas de question → ApiError", False)
except ka.ApiError as e:
    check("pas de question → 409, rien envoyé",
          e.code == 409 and not [c for c in calls if c[0] == "send-keys"])

# session absente → 404
ka._has_session = lambda rm_id: False
try:
    ka.op_approve({"rm_id": "42"})
    check("session absente → ApiError", False)
except ka.ApiError as e:
    check("session absente → 404", e.code == 404)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests approve RM2302 passent")
