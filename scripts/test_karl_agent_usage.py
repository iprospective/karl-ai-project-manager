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


# — _transcript_usage : total = entrée+sortie ; cache complémentaire ; dernier tour = contexte —
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
check("cache lu sommé (complémentaire)", u["cache_read"] == 15)
check("cache écrit sommé (complémentaire)", u["cache_creation"] == 3)
check("total = entrée+sortie (cache HORS total — RM2519)", u["total"] == 300 + 60)
check("tours comptés (assistant avec usage seulement)", u["turns"] == 2)
check("contexte courant = dernier tour (input+cache)", u["context_last"] == 200 + 10 + 0)
check("entrée ≠ sortie (différenciées)", u["input"] != u["output"])
# tour final à contexte nul (sortie seule) : ne réinitialise PAS le contexte courant
check("contexte courant ignore un tour final à contexte nul",
      ka._transcript_usage([_asst(200, 40, 10, 0), _asst(0, 15, 0, 0)])["context_last"] == 210)

# — RM2628 : une réponse écrite une fois par bloc de contenu ne compte qu'UNE fois —
def _asst_id(mid, i, o, cr=0, cc=0):
    return _l({"type": "assistant", "message": {"id": mid, "usage": {
        "input_tokens": i, "output_tokens": o,
        "cache_read_input_tokens": cr, "cache_creation_input_tokens": cc}}})


# Le JSONL écrit la MÊME réponse une fois par bloc (thinking, texte, tool_use),
# chaque ligne portant l'usage complet : sans dédup, ×3 sur la conso et le coût.
d = ka._transcript_usage([_asst_id("msg_a", 100, 30, 5, 2)] * 3)
check("RM2628 : 3 blocs d'une même réponse → sortie comptée une fois", d["output"] == 30)
check("RM2628 : idem pour l'entrée", d["input"] == 100)
check("RM2628 : idem pour le cache", d["cache_read"] == 5 and d["cache_creation"] == 2)
check("RM2628 : tours = réponses, pas lignes du JSONL", d["turns"] == 1)
check("RM2628 : contexte courant inchangé par la duplication",
      d["context_last"] == 100 + 5 + 2)
# Deux réponses distinctes, chacune dupliquée : les deux comptent, une fois chacune.
d2 = ka._transcript_usage([_asst_id("msg_a", 100, 30), _asst_id("msg_a", 100, 30),
                           _asst_id("msg_b", 200, 40), _asst_id("msg_b", 200, 40)])
check("RM2628 : réponses distinctes toutes comptées", d2["output"] == 70 and d2["turns"] == 2)
# Retry API : même id réémis avec un usage corrigé → on garde le dernier.
d3 = ka._transcript_usage([_asst_id("msg_a", 100, 30), _asst_id("msg_a", 100, 55)])
check("RM2628 : retry (même id) → dernier usage retenu", d3["output"] == 55)
# Sans id (lignes synthétiques) : pas de fusion abusive, chaque ligne compte.
d4 = ka._transcript_usage([_asst(10, 5), _asst(10, 5)])
check("RM2628 : messages sans id non fusionnés", d4["output"] == 10 and d4["turns"] == 2)

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

# — RM2609 : modèle extrait du transcript + coût depuis les tarifs —
_lines = [
    '{"type":"assistant","message":{"model":"claude-opus-4-8","usage":{"input_tokens":100,"output_tokens":40,"cache_read_input_tokens":900,"cache_creation_input_tokens":10}}}',
    '{"type":"user","message":{}}',
    '{"type":"assistant","message":{"model":"claude-opus-4-8","usage":{"input_tokens":50,"output_tokens":20,"cache_read_input_tokens":1200,"cache_creation_input_tokens":0}}}',
]
_u = ka._transcript_usage(_lines)
check("_transcript_usage capture le modèle", _u["model"] == "claude-opus-4-8")
check("_transcript_usage total = entrée+sortie", _u["total"] == 210 and _u["turns"] == 2)

_rates = {"input_per_mtok_usd": 10.0, "output_per_mtok_usd": 50.0,
          "cache_read_per_mtok_usd": 1.0, "cache_creation_per_mtok_usd": 12.5}
# input 150·10 + output 60·50 + cache_read 2100·1 + cache_creation 10·12.5 = 1500+3000+2100+125 = 6725 (µ$) → /1e6
_cost = ka._usage_cost(_u, _rates)
check("_usage_cost correct", abs(_cost - (6725 / 1_000_000)) < 1e-9)
check("_usage_cost sans tarifs → 0", ka._usage_cost(_u, None) == 0.0)
check("_usage_cost usage vide → 0", ka._usage_cost({}, _rates) == 0.0)
check("_usage_cost tolère champs manquants", ka._usage_cost({"input": 100}, {"input_per_mtok_usd": 10}) == 100 * 10 / 1_000_000)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests conso tokens session RM2373 + coût/modèle RM2609 passent")
