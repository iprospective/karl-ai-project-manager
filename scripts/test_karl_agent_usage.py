#!/usr/bin/env python3
"""Tests RM2373 — conso tokens de session différenciée entrée/sortie (op_usage).

Unitaire (sans tmux ni réseau) : _transcript_usage (agrégation pure), gardes
d'op_usage et résolution du transcript claude (JSONL) sur une session fabriquée.
Lancer : python3 scripts/test_karl_agent_usage.py
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


def _l(obj):
    return json.dumps(obj)


def _asst(i, o, cr=0, cc=0):
    return _l({"type": "assistant", "message": {"usage": {
        "input_tokens": i, "output_tokens": o,
        "cache_read_input_tokens": cr, "cache_creation_input_tokens": cc}}})


# — _transcript_usage : somme input/output/cache, dernier tour = contexte —
jsonl = [
    _l({"type": "user", "message": {"content": "va"}}),          # pas de usage
    _asst(100, 20, 5, 3),
    _l("ligne cassée"),                                          # ignorée
    _l({"type": "assistant", "message": {}}),                    # usage absent → ignoré
    _l({"type": "summary"}),                                     # pas assistant
    _asst(200, 40, 10, 0),
]
u = ka._transcript_usage(jsonl)
check("entrée sommée", u["input"] == 300)
check("sortie sommée", u["output"] == 60)
check("cache lu sommé", u["cache_read"] == 15)
check("cache écrit sommé", u["cache_creation"] == 3)
check("total = entrée+sortie+cache", u["total"] == 300 + 60 + 15 + 3)
check("tours comptés (assistant avec usage seulement)", u["turns"] == 2)
check("contexte courant = dernier tour (input+cache)", u["context_last"] == 200 + 10 + 0)
check("entrée ≠ sortie (différenciées)", u["input"] != u["output"])
# tour final à contexte nul (sortie seule) : ne réinitialise PAS le contexte courant
check("contexte courant ignore un tour final à contexte nul",
      ka._transcript_usage([_asst(200, 40, 10, 0), _asst(0, 15, 0, 0)])["context_last"] == 210)

# — bornages : transcript vide / sans tour assistant valide —
z = ka._transcript_usage([])
check("vide → tout à zéro", z["total"] == 0 and z["turns"] == 0 and z["context_last"] == 0)
check("champs None tolérés", ka._transcript_usage([
    _l({"type": "assistant", "message": {"usage": {"input_tokens": None, "output_tokens": 7}}})
])["output"] == 7)

# — op_usage : session claude fabriquée (JSONL dans un store) —
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2373-"))
store = tmp / "projstore"
store.mkdir(parents=True)
sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
(store / f"{sid}.jsonl").write_text("\n".join([_asst(100, 20, 5, 3), _asst(200, 40, 10, 0)]),
                                    encoding="utf-8")
ka.CLAUDE_STORES = [tmp]
ka._has_session = lambda rm_id: True
ka._key_info = lambda rm_id: {"engine": "claude", "session_id": sid}
d = ka.op_usage("42")
check("op_usage claude : source transcript", d["source"] == "transcript")
check("op_usage claude : agrégat entrée/sortie", d["usage"]["input"] == 300 and d["usage"]["output"] == 60)
check("op_usage claude : contexte courant", d["usage"]["context_last"] == 210)

# — moteur non-claude : usage vide, pas d'exception —
ka._key_info = lambda rm_id: {"engine": "shell", "session_id": None}
d2 = ka.op_usage("42")
check("op_usage non-claude : usage à zéro", d2["usage"]["total"] == 0 and d2["source"] == "none")

# — transcript introuvable (session claude neuve) : usage vide —
ka._key_info = lambda rm_id: {"engine": "claude", "session_id": "ffffffff-0000-0000-0000-000000000000"}
check("op_usage transcript absent : usage à zéro", ka.op_usage("42")["usage"]["total"] == 0)

# — gardes —
ka._has_session = lambda rm_id: False
try:
    ka.op_usage("999999")
    check("session absente → 404", False)
except ka.ApiError as e:
    check("session absente → 404", e.code == 404)
try:
    ka.op_usage("../etc")
    check("rm_id invalide → 400", False)
except ka.ApiError as e:
    check("rm_id invalide → 400", e.code == 400)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests conso tokens session RM2373 passent")
