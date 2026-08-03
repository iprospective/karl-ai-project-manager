#!/usr/bin/env python3
"""Tests de resolve_current_rm_id — attribution par scan transcript (RM1823).

Lancer : python3 scripts/test_pm_task_tick_resolve.py
WIP (pause 2026-06-03) : cas de base couverts. À compléter ce soir
(continuation, fallback sentinel, multi-tickets même tour, faux positifs).
"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_task_tick", str(_HERE / "pm-task-tick.py"))
tick = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tick)

# Hermétique (RM2524) : `_pick_from_events` écarte les tickets FERMÉS via `_is_closed`,
# qui lit le statut LIVE réel (PMConfig.find_task). Sans ça le test dérive au fil des
# fermetures (un id ouvert à l'écriture devient fermé → cas cassé). On pilote donc
# l'ensemble des « fermés » localement — défaut : aucun (tous ouverts).
_CLOSED = set()
tick._is_closed = lambda rm_id: rm_id in _CLOSED


# ── Helpers de construction de transcript synthétique ───────────────────────
def human(text):
    return {"message": {"role": "user", "content": text}}

def a_text(text):
    return {"message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}

def a_bash(cmd):
    return {"message": {"role": "assistant",
                        "content": [{"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]}}

def a_edit(fp, name="Edit"):
    return {"message": {"role": "assistant",
                        "content": [{"type": "tool_use", "name": name, "input": {"file_path": fp}}]}}

def a_skill(skill, args):
    return {"message": {"role": "assistant",
                        "content": [{"type": "tool_use", "name": "Skill",
                                     "input": {"skill": skill, "args": args}}]}}

def tool_result(text="ok"):
    return {"message": {"role": "user", "content": [{"type": "tool_result", "content": text}]}}


def write(events):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return path


def resolve(events):
    p = write(events)
    try:
        return tick._resolve_from_transcript(p)
    finally:
        os.unlink(p)


# ── Cas ─────────────────────────────────────────────────────────────────────
CASES = []
def case(name):
    def deco(fn):
        CASES.append((name, fn)); return fn
    return deco


@case("mutation PM positionnelle → id")
def _():
    rid, reason = resolve([human("commente"), a_bash("/x/pm-task-comment.py 1822 --note hi"), tool_result()])
    assert rid == 1822, (rid, reason)
    assert "signal=3" in reason, reason


@case("mutation PM --rm-id → id")
def _():
    rid, _r = resolve([human("report"), a_bash("scripts/pm-task-report.py --rm-id 1669 --apply"), tool_result()])
    assert rid == 1669, rid


@case("multi-tickets : le tour courant gagne (B), pas A du tour précédent")
def _():
    rid, _r = resolve([
        human("bosse sur A"), a_bash("pm-task-status-update.py 1111 en_cours"), tool_result(),
        human("maintenant B"), a_bash("pm-task-comment.py 2222 --note x"), tool_result(),
    ])
    assert rid == 2222, rid


@case("tour sans ticket → continuation du dernier de la session")
def _():
    rid, reason = resolve([
        human("bosse A"), a_bash("pm-task-comment.py 1111 --note x"), tool_result(),
        human("question annexe"), a_text("réponse sans ticket"),
    ])
    assert rid == 1111, rid
    assert "continuation" in reason, reason


@case("force du signal : édition fichier (2) bat mention texte (1)")
def _():
    rid, _r = resolve([human("x"), a_text("cf RM1111"), a_edit("/p/tasks/RM2222_foo.md"), tool_result()])
    assert rid == 2222, rid


@case("skill mmi-pm → id (signal fort)")
def _():
    rid, _r = resolve([human("passe en cours"),
                       a_skill("mmi-pm-task-status-update", "1822 en_cours"), tool_result()])
    assert rid == 1822, rid


@case("création (pm-task-add sans id) → pas d'attribution")
def _():
    rid, _r = resolve([human("crée"),
                       a_bash("pm-task-add.py --project iprospective/pm-ai-agents --title 'Setup CI 2024'")])
    assert rid is None, rid


@case("RM2053 : tour touchant fermé + ouvert → ticke l'ouvert")
def _():
    _CLOSED.add(3333)
    try:
        rid, _r = resolve([human("x"),
                           a_bash("pm-task-comment.py 3333 --note ferme"),
                           a_bash("pm-task-comment.py 4444 --note ouvert"), tool_result()])
        assert rid == 4444, rid
    finally:
        _CLOSED.discard(3333)


@case("RM2053 : tour ne touchant que du fermé → aucune attribution")
def _():
    _CLOSED.add(3333)
    try:
        rid, _r = resolve([human("x"), a_bash("pm-task-comment.py 3333 --note ferme"), tool_result()])
        assert rid is None, rid
    finally:
        _CLOSED.discard(3333)


if __name__ == "__main__":
    fails = 0
    for name, fn in CASES:
        try:
            fn(); print(f"  ✓ {name}")
        except AssertionError as e:
            fails += 1; print(f"  ✗ {name} — {e}")
    print(f"\n{len(CASES) - fails}/{len(CASES)} ok")
    sys.exit(1 if fails else 0)
