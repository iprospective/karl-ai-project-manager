#!/usr/bin/env python3
"""Tests RM2330 — outline de conversation + navigation dans l'historique.

Unitaire (sans tmux ni réseau) : _conversation_outline (pure), gardes
d'op_outline/op_scroll et séquence copy-mode d'op_scroll.
Lancer : python3 scripts/test_karl_agent_outline.py
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


# — parsing : user (> …), multi-ligne groupé, assistant (⏺), bruit ignoré —
text = """bruit de terminal
> corrige le bug du parseur
> et ajoute un test
⏺ Je regarde le parseur.
  détail indenté sans marqueur
⏺ Corrigé — le test passe.
> merci, déploie
"""
items = ka._conversation_outline(text)
check("3 messages user + 2 assistant",
      [i["kind"] for i in items] == ["user", "assistant", "assistant", "user"])
check("message user multi-ligne groupé en un item",
      items[0]["text"] == "corrige le bug du parseur et ajoute un test")
check("ligne du 1er item = 1re ligne du bloc", items[0]["line"] == 1)
check("texte assistant nettoyé du ⏺", items[1]["text"] == "Je regarde le parseur.")
check("dernier item = dernier message user", items[-1]["text"] == "merci, déploie")

# — bornages —
check("texte tronqué à 120", all(len(i["text"]) <= 120 for i in ka._conversation_outline(
    "> " + "x" * 300 + "\n⏺ " + "y" * 300)))
many = "\n".join(f"> message {i}\n⏺ ok {i}" for i in range(900))   # 1800 items alternés
check("max 800 items, les plus récents", len(ka._conversation_outline(many)) == 800
      and ka._conversation_outline(many)[-1]["text"] == "ok 899")
check("scrollback vide → []", ka._conversation_outline("") == [])

# — _transcript_outline : source claude (JSONL) — messages texte seuls —
import json as _json


def _l(obj):
    return _json.dumps(obj)


jsonl = [
    _l({"type": "user", "message": {"content": "corrige le parseur"}}),
    _l({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Je corrige."}, {"type": "tool_use", "name": "Bash"}]}}),
    _l({"type": "user", "message": {"content": [
        {"type": "tool_result", "content": "sortie d'outil"}]}}),      # pas un message
    _l({"type": "user", "isMeta": True, "message": {"content": "méta"}}),
    _l({"type": "user", "message": {"content": "<command-name>/clear</command-name>"}}),
    _l("ligne cassée pas du json objet"),
    _l({"type": "assistant", "message": {"content": [{"type": "text", "text": "Fini ✔"}]}}),
    _l({"type": "user", "message": {"content": "merci " + "x" * 300}}),
]
ti = ka._transcript_outline(jsonl)
check("transcript : 4 messages retenus (texte seulement)",
      [i["kind"] for i in ti] == ["user", "assistant", "assistant", "user"])
check("transcript : tool_result / méta / enveloppes <…> exclus",
      all("outil" not in i["text"] and "méta" not in i["text"] and "command" not in i["text"] for i in ti))
check("transcript : aperçu 120c + full conservé",
      len(ti[3]["text"]) <= 120 and ti[3]["full"].startswith("merci ") and len(ti[3]["full"]) <= 4000)
check("transcript : n séquentiel", [i["n"] for i in ti] == [0, 1, 2, 3])
check("transcript : cap max_items (plus récents)",
      len(ka._transcript_outline(jsonl * 300, max_items=100)) == 100)

# — op_scroll : séquence copy-mode déterministe —
calls = []


def fake_tmux(*args, timeout=10):
    calls.append(args)
    return 0, "", ""


ka._tmux = fake_tmux
ka._has_session = lambda rm_id: True
ka.op_scroll({"rm_id": "42", "line": 7})
check("scroll : copy-mode → history-top → scroll-down N",
      calls[0][0] == "copy-mode"
      and ("-X", "history-top") == calls[1][-2:]
      and ("-N", "7", "-X", "scroll-down") == calls[2][-4:])
calls.clear()
ka.op_scroll({"rm_id": "42", "line": 0})
check("scroll ligne 0 : pas de scroll-down", all("scroll-down" not in c for c in calls))
calls.clear()
r = ka.op_scroll({"rm_id": "42", "bottom": True})
check("bottom : cancel du copy-mode → direct",
      r["position"] == "live" and ("-X", "cancel") == calls[0][-2:])

# — gardes —
try:
    ka.op_scroll({"rm_id": "42", "line": "abc"})
    check("line invalide → 400", False)
except ka.ApiError as e:
    check("line invalide → 400", e.code == 400)
try:
    ka.op_scroll({"rm_id": "42", "line": -3})
    check("line négative → 400", False)
except ka.ApiError as e:
    check("line négative → 400", e.code == 400)
ka._has_session = lambda rm_id: False
try:
    ka.op_outline("999999")
    check("outline session absente → 404", False)
except ka.ApiError as e:
    check("outline session absente → 404", e.code == 404)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests outline RM2330 passent")
