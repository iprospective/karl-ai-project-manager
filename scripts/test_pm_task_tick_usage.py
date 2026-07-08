#!/usr/bin/env python3
"""Tests de extract_turn_usage — somme du tour avec curseur par session (RM2161).

Le bug corrigé : seul le DERNIER message assistant du transcript était compté à
chaque Stop → sous-comptage massif de l'output sur les tours longs multi-outils.

Lancer : python3 scripts/test_pm_task_tick_usage.py
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_task_tick", str(_HERE / "pm-task-tick.py"))
tick = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tick)

# Curseurs redirigés vers un tempdir (ne pas toucher ~/.claude/logs)
_TMP = Path(tempfile.mkdtemp(prefix="tick-usage-test-"))
tick.TURN_START_DIR = _TMP


# ── Helpers ──────────────────────────────────────────────────────────────────
def human(text):
    return {"message": {"role": "user", "content": text}}


def assistant(msg_id, output=100, inp=5, cache_read=1000, cache_creation=50, model="claude-test-1"):
    return {"message": {"role": "assistant", "id": msg_id, "model": model,
                        "usage": {"input_tokens": inp, "output_tokens": output,
                                  "cache_read_input_tokens": cache_read,
                                  "cache_creation_input_tokens": cache_creation},
                        "content": [{"type": "text", "text": "..."}]}}


def write_transcript(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


_fails = []


def check(name, got, expected):
    ok = got == expected
    print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f" — attendu {expected}, obtenu {got}"))
    if not ok:
        _fails.append(name)


# ── Scénarios ────────────────────────────────────────────────────────────────
def test_fresh_session_sums_whole_turn():
    """1er Stop, pas de curseur : somme TOUS les messages assistant du tour
    (l'ancien code n'aurait compté que le dernier : output=30)."""
    print("fresh_session_sums_whole_turn")
    t = _TMP / "t1.jsonl"
    write_transcript(t, [human("go"), assistant("m1", output=10),
                         assistant("m2", output=20), assistant("m3", output=30)])
    u = tick.extract_turn_usage(t, "s1")
    check("output = 10+20+30", u["output"], 60)
    check("cache_read sommé", u["cache_read"], 3000)
    check("model", u["model"], "claude-test-1")


def test_cursor_counts_only_new_turn():
    """2e Stop : le curseur posé au Stop précédent exclut le tour déjà tické."""
    print("cursor_counts_only_new_turn")
    t = _TMP / "t2.jsonl"
    ev = [human("go"), assistant("m1", output=10), assistant("m2", output=20)]
    write_transcript(t, ev)
    tick.extract_turn_usage(t, "s2")  # Stop 1 → curseur en fin de fichier
    ev += [human("suite"), assistant("m3", output=40), assistant("m4", output=50)]
    write_transcript(t, ev)
    u = tick.extract_turn_usage(t, "s2")  # Stop 2
    check("output = 40+50 (tour 1 exclu)", u["output"], 90)


def test_midturn_injected_human_not_lost():
    """Message humain injecté EN COURS de tour : avec curseur, la fenêtre part du
    Stop précédent, pas du dernier prompt → rien n'est perdu."""
    print("midturn_injected_human_not_lost")
    t = _TMP / "t3.jsonl"
    ev = [human("go"), assistant("m1", output=10)]
    write_transcript(t, ev)
    tick.extract_turn_usage(t, "s3")  # Stop 1
    ev += [human("tour 2"), assistant("m2", output=20),
           human("injecté pendant le travail"), assistant("m3", output=30)]
    write_transcript(t, ev)
    u = tick.extract_turn_usage(t, "s3")  # Stop 2
    check("output = 20+30 (pas seulement depuis l'injection)", u["output"], 50)


def test_retry_dedup_keeps_last():
    """Retry API : même message.id ré-émis → compté une fois (dernier usage)."""
    print("retry_dedup_keeps_last")
    t = _TMP / "t4.jsonl"
    write_transcript(t, [human("go"), assistant("mA", output=100),
                         assistant("mA", output=120), assistant("mB", output=7)])
    u = tick.extract_turn_usage(t, "s4")
    check("output = 120+7 (mA dédupliqué)", u["output"], 127)


def test_resume_without_cursor_counts_last_turn_only():
    """Session reprise (--resume) : transcript plein d'historique, pas de curseur
    → fenêtre = dernier prompt humain, on ne recompte pas l'historique."""
    print("resume_without_cursor_counts_last_turn_only")
    t = _TMP / "t5.jsonl"
    write_transcript(t, [human("vieux tour 1"), assistant("m1", output=500),
                         human("vieux tour 2"), assistant("m2", output=600),
                         human("reprise"), assistant("m3", output=30)])
    u = tick.extract_turn_usage(t, "s5-new")
    check("output = 30 (historique ignoré)", u["output"], 30)


def test_invalid_cursor_falls_back():
    """Curseur au-delà du fichier (transcript réécrit/tronqué) → fallback tour
    courant, jamais de recomptage depuis 0."""
    print("invalid_cursor_falls_back")
    t = _TMP / "t6.jsonl"
    write_transcript(t, [human("go")] + [assistant(f"m{i}", output=10) for i in range(10)])
    tick.extract_turn_usage(t, "s6")  # curseur ligne 11
    write_transcript(t, [human("nouveau"), assistant("mX", output=5)])  # 2 lignes
    u = tick.extract_turn_usage(t, "s6")
    check("output = 5 (fallback, pas de double-comptage)", u["output"], 5)


def test_no_new_assistant_returns_none_but_advances():
    """Stop sans nouveau message assistant → None ; le curseur avance quand même
    (la conso d'un tour untracked n'est pas réattribuée au ticket suivant)."""
    print("no_new_assistant_returns_none_but_advances")
    t = _TMP / "t7.jsonl"
    ev = [human("go"), assistant("m1", output=10)]
    write_transcript(t, ev)
    check("1er Stop compte", tick.extract_turn_usage(t, "s7")["output"], 10)
    check("2e Stop sans nouveauté → None", tick.extract_turn_usage(t, "s7"), None)
    ev += [assistant("m2", output=20)]
    write_transcript(t, ev)
    check("3e Stop ne compte que m2", tick.extract_turn_usage(t, "s7")["output"], 20)


def test_cursor_isolated_per_session():
    """Deux sessions sur des transcripts distincts n'interfèrent pas."""
    print("cursor_isolated_per_session")
    ta, tb = _TMP / "t8a.jsonl", _TMP / "t8b.jsonl"
    write_transcript(ta, [human("a"), assistant("a1", output=11)])
    write_transcript(tb, [human("b"), assistant("b1", output=22)])
    check("session A", tick.extract_turn_usage(ta, "s8a")["output"], 11)
    check("session B", tick.extract_turn_usage(tb, "s8b")["output"], 22)


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    if _fails:
        sys.exit(f"\n✗ {len(_fails)} échec(s) : {', '.join(_fails)}")
    print("\n✓ tous les tests passent")
