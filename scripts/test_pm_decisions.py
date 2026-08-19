#!/usr/bin/env python3
"""Tests RM2305 — extraction et rendu des décisions de session.

Unitaire sur les fonctions pures (aucun transcript ni ticket réel).
Lancer : python3 scripts/test_pm_decisions.py
"""
import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("pm_decisions", HERE / "pm-decisions.py")
pd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pd)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def _ask(uid, *questions):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": uid, "name": "AskUserQuestion", "input": {"questions": [
            {"question": q, "options": [{"label": "Option A"}, {"label": "Option B"}]}
            for q in questions]}}]}})


def _res(uid, content):
    return json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": uid, "content": content}]}})


# — extraction —
d = pd.session_decisions([
    _ask("t1", "On garde l'ancien nom ?"),
    _res("t1", 'Your questions have been answered: "On garde l\'ancien nom ?"="Non". Continue.'),
    _ask("t2", "On livre maintenant ?"),          # jamais répondue
    json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Faut-il aussi renommer le dossier ?"}]}}),  # prose
])
check("une question tranchée porte sa réponse", d[0] == ("On garde l'ancien nom ?", "Non"))
check("une question sans réponse est retenue, avec None",
      d[1] == ("On livre maintenant ?", None))
check("une question posée EN PROSE n'est pas une décision", len(d) == 2)

# les options proposées ne doivent pas polluer le libellé de la question
check("le libellé garde la question, pas le menu d'options",
      "Option A" not in d[0][0] and "Option B" not in d[0][0])

multi = pd.session_decisions([
    _ask("t3", "Quel emplacement ?", "Quel geste ?"),
    _res("t3", 'Your questions have been answered: "Quel emplacement ?"="En bas", '
               '"Quel geste ?"="Entrée". Continue.'),
])
check("questions et réponses multiples restent appariées",
      multi[0] == ("Quel emplacement ? / Quel geste ?", "En bas / Entrée"))

for cas, contenu in (("rejet", "The user doesn't want to proceed with this tool use."),
                     ("interruption", "[Request interrupted by user for tool use]")):
    ko = pd.session_decisions([_ask("t4", "On continue ?"), _res("t4", contenu)])
    check(f"{cas} → question sans réponse, aucune décision inventée",
          ko == [("On continue ?", None)])

check("session sans question → aucune décision", pd.session_decisions([]) == [])

# — rendu —
r = pd.render_entry([("Q tranchée", "R retenue"), ("Q ouverte", None)], "sess-1", "2026-01-01T10:00")
check("le rendu compte tranchées et sans réponse séparément",
      "1 tranchée(s)" in r and "1 restée(s) sans réponse" in r)
check("la décision montre la réponse retenue", "Q tranchée" in r and "→ R retenue" in r)
check("une question sans réponse est MARQUÉE, pas omise",
      "Q ouverte" in r and "restée sans réponse" in r)
check("l'entrée est datée et rattachée à sa session",
      "2026-01-01T10:00" in r and "sess-1" in r)
check("le bloc s'append proprement (séparé de ce qui précède)", r.startswith("\n\n## "))

long_q = "x" * 500
r2 = pd.render_entry([(long_q, "ok")], "s", "t")
check("une question très longue est tronquée, pas déversée telle quelle",
      "…" in r2 and len(r2) < 500)

r3 = pd.render_entry([], "s", "t")
check("aucune décision → un bloc honnête plutôt qu'une entrée vide",
      "0 tranchée(s)" in r3)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests décisions RM2305 passent")
