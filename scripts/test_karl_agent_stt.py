#!/usr/bin/env python3
"""Tests RM2533 (vocal V2 L2) — STT serveur Whisper : caps, gardes op_stt, forward.

Unitaire, SANS sidecar réel : la détection stt et le forward sont mockés (le
sidecar faster-whisper est validé en intégration — cf. spike + .log.md). Les
gardes d'entrée (audio vide / b64 invalide / trop gros) échouent avant tout
appel réseau. Lancer : python3 scripts/test_karl_agent_stt.py
"""
import base64
import importlib.util
import pathlib
import sys
import urllib.request

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


# — caps : sidecar injoignable (port mort) → stt False, réel (pas de mock) —
ka.WHISPER_URL = "http://127.0.0.1:59999"   # port non écouté → connexion refusée → None
caps = ka.op_voice_caps()
check("caps sidecar absent : stt False", caps["stt"] is False and caps["stt_engine"] is None)

# — caps : sidecar chaud (health mocké) → stt True, engine whisper —
ka._whisper_health = lambda timeout=0.4: {"ok": True, "warm": True, "model": "small"}
caps2 = ka.op_voice_caps()
check("caps sidecar chaud : stt True", caps2["stt"] is True and caps2["stt_engine"] == "whisper")

# health froid (warm False) → non prêt
ka._whisper_health = lambda timeout=0.4: None
check("_whisper_ready False si froid/absent", ka._whisper_ready() is False)

# — gardes d'entrée op_stt (avant tout réseau) —
expect_api(400, lambda: ka.op_stt({"audio_b64": ""}), "audio vide → 400")
expect_api(400, lambda: ka.op_stt({}), "audio_b64 manquant → 400")
expect_api(400, lambda: ka.op_stt({"audio_b64": "@@ pas du base64 @@"}), "b64 invalide → 400")
_saved_max = ka.STT_MAX_BYTES
ka.STT_MAX_BYTES = 4                          # abaisse la borne pour tester 413 sans gros buffer
expect_api(413, lambda: ka.op_stt({"audio_b64": base64.b64encode(b"trop long").decode()}),
           "audio trop gros → 413")
ka.STT_MAX_BYTES = _saved_max

# — sidecar injoignable pendant op_stt (audio valide) → 503 —
ka.WHISPER_URL = "http://127.0.0.1:59999"
expect_api(503, lambda: ka.op_stt({"audio_b64": base64.b64encode(b"abc").decode()}),
           "sidecar injoignable → 503")


# — forward nominal : urlopen mocké → texte remonté —
class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def read(self):
        import json as _j
        return _j.dumps(self._p).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_captured = {}


def _fake_urlopen(req, timeout=None):
    _captured["url"] = req.full_url
    _captured["data"] = req.data
    return _FakeResp({"text": "envoie le rapport", "lang": "fr", "duration": 2.1})


_real_urlopen = urllib.request.urlopen
urllib.request.urlopen = _fake_urlopen
try:
    res = ka.op_stt({"audio_b64": base64.b64encode(b"\x00\x01\x02audio").decode(), "lang": "fr"})
    check("forward : texte transcrit remonté", res["text"] == "envoie le rapport")
    check("forward : langue remontée", res["lang"] == "fr")
    check("forward : ?lang=fr dans l'URL sidecar", _captured["url"].endswith("/stt?lang=fr"))
    check("forward : corps = octets audio bruts", _captured["data"] == b"\x00\x01\x02audio")
finally:
    urllib.request.urlopen = _real_urlopen

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests STT serveur RM2533 passent")
