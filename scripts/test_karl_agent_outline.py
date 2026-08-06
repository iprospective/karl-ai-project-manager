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

# — RM2549 : questions / réponses typées, état résolu —


def _ask(uid, *questions):
    """Un tool_use AskUserQuestion, tel qu'écrit dans le transcript."""
    return _l({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Deux façons de faire."},
        {"type": "tool_use", "id": uid, "name": "AskUserQuestion", "input": {"questions": [
            {"question": q, "options": [{"label": "Option A"}, {"label": "Option B"}]}
            for q in questions]}}]}})


def _res(uid, content):
    return _l({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": uid, "content": content}]}})


qa = ka._transcript_outline([
    _ask("t1", "Où placer le composer ?"),
    _res("t1", 'Your questions have been answered: "Où placer le composer ?"='
               '"Barre permanente" selected preview:\n┌──┐. You can now continue.'),
])
check("RM2549 : texte assistant AVANT sa question (ordre chronologique)",
      [i["kind"] for i in qa] == ["assistant", "question", "answer"])
check("RM2549 : la question porte le texte posé",
      qa[1]["text"] == "Où placer le composer ?")
check("RM2549 : le détail liste les options proposées",
      "Option A" in qa[1]["full"] and "Option B" in qa[1]["full"])
check("RM2549 : question répondue → resolved + réponse retenue",
      qa[1]["resolved"] is True and qa[1]["answer"] == "Barre permanente")
check("RM2549 : la réponse est un item distinct, avec le choix retenu",
      qa[2]["kind"] == "answer" and qa[2]["text"] == "Barre permanente")
check("RM2549 : n séquentiel avec les nouveaux items",
      [i["n"] for i in qa] == [0, 1, 2])

multi = ka._transcript_outline([
    _ask("t2", "Quel emplacement ?", "Quel geste d'envoi ?"),
    _res("t2", 'Your questions have been answered: "Quel emplacement ?"="Sous le terminal", '
               '"Quel geste d\'envoi ?"="Entrée envoie". You can now continue.'),
])
check("RM2549 : questions multiples jointes, réponses multiples jointes",
      multi[1]["text"] == "Quel emplacement ? / Quel geste d'envoi ?"
      and multi[1]["answer"] == "Sous le terminal / Entrée envoie")

# une question posée dont le transcript s'arrête là : la session ATTEND encore
attente = ka._transcript_outline([_ask("t3", "On continue malgré l'écart ?")])
check("RM2549 : question sans résultat → non résolue, sans item réponse",
      [i["kind"] for i in attente] == ["assistant", "question"]
      and attente[1]["resolved"] is False and attente[1]["answer"] is None)

for cas, contenu in (
        ("rejet", "The user doesn't want to proceed with this tool use. The tool use was rejected"),
        ("interruption", "[Request interrupted by user for tool use]")):
    ko = ka._transcript_outline([_ask("t4", "On garde ce nom ?"), _res("t4", contenu)])
    check(f"RM2549 : {cas} → la question reste non résolue, aucune réponse inventée",
          [i["kind"] for i in ko] == ["assistant", "question"]
          and ko[1]["resolved"] is False and ko[1]["answer"] is None)

plan = ka._transcript_outline([
    _l({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t5", "name": "ExitPlanMode",
         "input": {"plan": "1. lire\n2. corriger"}}]}}),
    _res("t5", "User has approved your plan."),
])
check("RM2549 : ExitPlanMode = question, plan conservé en détail",
      plan[0]["kind"] == "question" and "Plan proposé" in plan[0]["text"]
      and "2. corriger" in plan[0]["full"] and plan[0]["resolved"] is True)

# non-régression : les tool_result ORDINAIRES restent hors de l'outline
ordinaire = ka._transcript_outline([
    _l({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "ls"}}]}}),
    _res("b1", "fichier1\nfichier2"),
])
check("RM2549 : un appel d'outil ordinaire n'entre pas dans l'outline", ordinaire == [])

# aucune divination : une question POSÉE EN PROSE n'est pas typée
prose = ka._transcript_outline([
    _l({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Faut-il garder l'ancien nom ? Dis-moi."}]}})])
check("RM2549 : question en prose → message assistant ordinaire, pas 'question'",
      [i["kind"] for i in prose] == ["assistant"] and prose[0]["resolved"] is None)

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
