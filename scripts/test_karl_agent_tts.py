#!/usr/bin/env python3
"""Tests RM2532 (vocal V2 L1) — TTS serveur Piper : détection modèles, caps, gardes.

Unitaire, SANS Piper installé : détection des modèles (fichiers factices), capacités,
et gardes de op_tts_wav (texte vide/trop long → 400, Piper absent → 503). La synthèse
réelle est validée en intégration (cf. .log.md). Lancer : python3 scripts/test_karl_agent_tts.py
"""
import importlib.util
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


def expect_api(code, fn, name):
    try:
        fn()
        check(name, False)
    except ka.ApiError as e:
        check(name, e.code == code)


# — Piper absent (défaut du test) : caps tts=False, synth → 503 —
ka.PIPER_BIN = pathlib.Path("/nonexistent/piper")
ka.PIPER_MODELS = pathlib.Path("/nonexistent/models")
# Herméticité (RM2531) : op_voice_caps sonde le sidecar Whisper en direct → on le
# pointe sur un port mort pour que stt=False quel que soit l'environnement (sinon
# le test échoue quand un sidecar tourne vraiment, ex. activation prod RM2533).
ka.WHISPER_URL = "http://127.0.0.1:9"
caps = ka.op_voice_caps()
check("caps sans Piper : tts False", caps["tts"] is False and caps["engine"] is None)
check("caps : stt False (lot 2)", caps["stt"] is False)
expect_api(503, lambda: ka.op_tts_wav({"text": "bonjour"}), "Piper absent → 503")

# — détection des modèles : paire .onnx + .onnx.json, langue = préfixe du nom —
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2532-"))
(tmp / "fr_FR-siwis-medium.onnx").write_bytes(b"x")
(tmp / "fr_FR-siwis-medium.onnx.json").write_text("{}")
(tmp / "en_US-lessac-medium.onnx").write_bytes(b"x")
(tmp / "en_US-lessac-medium.onnx.json").write_text("{}")
(tmp / "orphelin.onnx").write_bytes(b"x")          # sans .json → ignoré
ka.PIPER_MODELS = tmp
models = ka._piper_models()
check("modèle fr détecté", "fr" in models and models["fr"].name.startswith("fr_FR"))
check("modèle en détecté", "en" in models)
check("onnx sans json ignoré", "or" not in models and len(models) == 2)

# caps avec modèles + binaire présents (binaire = ce script, juste pour l'existence)
ka.PIPER_BIN = HERE / "test_karl_agent_tts.py"
caps2 = ka.op_voice_caps()
check("caps avec modèles+bin : tts True", caps2["tts"] is True and caps2["engine"] == "piper")
check("caps : langues triées", caps2["tts_langs"] == ["en", "fr"])

# — gardes d'entrée (avant même l'appel Piper) —
expect_api(400, lambda: ka.op_tts_wav({"text": ""}), "texte vide → 400")
expect_api(400, lambda: ka.op_tts_wav({"text": "x" * 5000}), "texte trop long → 400")

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests TTS serveur RM2532 passent")
