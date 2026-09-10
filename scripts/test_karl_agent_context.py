#!/usr/bin/env python3
"""Tests RM3082 — occupation de contexte servie par tuile de session.

Ce qui casserait en silence :
  - lire le contexte par `/usage/<id>` (fichier ENTIER) au lieu de la queue déjà lue et cachée :
    invisible à l'œil, ruineux à chaque tick sur des transcripts de centaines de Mo ;
  - prendre le DERNIER tour même quand il n'a pas de contexte (sortie seule) → jauge qui retombe
    à zéro un tour sur deux ;
  - inventer une valeur quand la queue ne contient aucun tour → un pourcentage faux, pire que rien ;
  - des seuils croisés (90/50/75) : aucune erreur, mais une jauge incompréhensible.

Lancer : python3 scripts/test_karl_agent_context.py
"""
import importlib.util
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core                     # noqa: E402
hermetic_core()

spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec); sys.modules["karl_agent"] = ka; spec.loader.exec_module(ka)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def turn(model="claude-opus-5", **u):
    return json.dumps({"type": "assistant", "message": {"model": model, "usage": u}})


tmp = pathlib.Path(tempfile.mkdtemp(prefix="karl-ctx-"))


def transcript(name, lines):
    f = tmp / name
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


# ── le contexte vient du dernier tour SIGNIFICATIF ───────────────────────────
f = transcript("plein.jsonl", [
    json.dumps({"type": "custom-title", "customTitle": "[WIP] Essai"}),
    turn(input_tokens=10, cache_read_input_tokens=90000, cache_creation_input_tokens=1000, output_tokens=400),
    json.dumps({"type": "user", "cwd": "/tmp/w", "message": {"content": "suite"}}),
    turn(input_tokens=12, cache_read_input_tokens=150000, cache_creation_input_tokens=2000, output_tokens=800),
    turn(output_tokens=25),                     # sortie seule : ne remplace pas le contexte connu
])
m = ka._jsonl_tail_meta(f)
check("contexte = entrée + cache lu + cache écrit du dernier tour utile", m["context"] == 152012, str(m["context"]))
check("un tour sans contexte ne fait pas retomber la jauge", m["context"] != 25)
check("le modèle voyage avec", m["model"] == "claude-opus-5", str(m.get("model")))
check("le titre et le cwd restent lus dans la même passe", m["title"] == "[WIP] Essai" and m["cwd"] == "/tmp/w")

# ── absence de donnée : rien, jamais un chiffre inventé ──────────────────────
f2 = transcript("muet.jsonl", [json.dumps({"type": "user", "message": {"content": "bonjour"}})])
check("aucun tour assistant dans la queue → context None", ka._jsonl_tail_meta(f2)["context"] is None)
f3 = transcript("vide.jsonl", ["", "pas du json"])
check("lignes illisibles → context None, sans exception", ka._jsonl_tail_meta(f3)["context"] is None)

# ── la lecture reste BORNÉE et cachée ───────────────────────────────────────
gros = transcript("gros.jsonl", [json.dumps({"type": "user", "message": {"content": "x" * 2000}})] * 200
                  + [turn(input_tokens=5, cache_read_input_tokens=120000, cache_creation_input_tokens=0)])
check("un transcript volumineux rend quand même son dernier tour (queue lue, pas le fichier entier)",
      ka._jsonl_tail_meta(gros)["context"] == 120005, str(ka._jsonl_tail_meta(gros)["context"]))
before = dict(ka._tail_cache)
ka._jsonl_tail_meta(gros)
check("second appel : servi par le cache (même mtime), aucune relecture", ka._tail_cache.keys() == before.keys())

# ── les seuils : ordonnés de force ───────────────────────────────────────────
th = ka._context_thresholds()
check("trois paliers, ordonnés, valeurs par défaut", th == {"warn": 50, "high": 75, "crit": 90}, str(th))
saved = ka._pm_settings


def fake_settings(*a, **k):
    return [{"key": "conf:sessions.context_warn_pct", "value": 90},
            {"key": "conf:sessions.context_high_pct", "value": 50},
            {"key": "conf:sessions.context_critical_pct", "value": 75}]


ka._pm_settings = fake_settings
th2 = ka._context_thresholds()
ka._pm_settings = saved
check("des seuils saisis dans le désordre sont remis en ordre", th2 == {"warn": 50, "high": 75, "crit": 90}, str(th2))

# ── le contrat servi au front ────────────────────────────────────────────────
src = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("la tuile est alimentée par la lecture de queue, pas par /usage",
      's["context"] = cx["context"]' in src and "_transcript_context(s.get(\"session_id\")" in src)
check("les paliers sont exposés au front (cockpit-config)", '"context_thresholds": _context_thresholds()' in src)
check("les trois seuils sont dans la whitelist des réglages",
      all(f'conf:sessions.context_{k}_pct' in src for k in ("warn", "high", "critical")))

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — contexte par session (RM3082)")
