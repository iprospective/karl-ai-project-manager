#!/usr/bin/env python3
"""karl-whisper — sidecar STT local pour le cockpit (RM2533, vocal V2 L2).

Pourquoi un sidecar séparé et pas dans karl-agent ? faster-whisper charge un
modèle de 0,5–1,5 Go en RAM qu'il faut garder **chaud** (le rechargement à
chaque dictée coûterait ~1 s) : on isole donc ce cycle de vie et cette RAM dans
un service systemd user dédié, appelé en localhost par karl-agent. Absent →
`/voice/caps` annonce `stt:false` et le cockpit retombe sur la Web Speech API du
navigateur (aucune régression sur V1 — RM2329/2350).

Décodage audio : faster-whisper décode via **PyAV** (les wheels pip embarquent
ffmpeg) — le webm/opus de MediaRecorder passe donc sans binaire ffmpeg système.

Endpoints (bind 127.0.0.1 EN DUR — invariant sécu, comme karl-agent) :
  GET  /health           → {ok, model, device, compute, warm}
  POST /stt?lang=fr      → corps = octets audio bruts (webm/opus/wav/…)
                           → {text, lang, duration}

Config (env, posée par l'unité systemd) :
  KARL_WHISPER_PORT     (défaut 9877)
  KARL_WHISPER_MODEL    (défaut « small » — voir bench L3 RM2534)
  KARL_WHISPER_DEVICE   (défaut « cpu »)
  KARL_WHISPER_COMPUTE  (défaut « int8 »)
  KARL_WHISPER_LANG     (défaut « fr » ; vide = auto-détection)
  KARL_WHISPER_MAX_MB   (défaut 25 — garde-fou taille du clip)

Lancer :  python karl-whisper-sidecar.py   (via le venv qui a faster-whisper)
"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("KARL_WHISPER_PORT") or 9877)
MODEL = os.environ.get("KARL_WHISPER_MODEL") or "small"
DEVICE = os.environ.get("KARL_WHISPER_DEVICE") or "cpu"
COMPUTE = os.environ.get("KARL_WHISPER_COMPUTE") or "int8"
DEFAULT_LANG = os.environ.get("KARL_WHISPER_LANG", "fr") or None
MAX_BYTES = int(float(os.environ.get("KARL_WHISPER_MAX_MB") or 25) * 1024 * 1024)

# Modèle chargé une seule fois au démarrage (chaud). La transcription CPU est
# sérialisée par _LOCK : « file 1-à-la-fois » (CDC RM2351) — un WhisperModel
# CTranslate2 n'est pas garanti thread-safe et le CPU sature de toute façon.
_MODEL = None
_LOCK = threading.Lock()


def _load_model():
    global _MODEL
    from faster_whisper import WhisperModel  # import tardif : erreur claire si absent
    sys.stderr.write(f"[karl-whisper] chargement modèle {MODEL} ({DEVICE}/{COMPUTE})…\n")
    sys.stderr.flush()
    _MODEL = WhisperModel(MODEL, device=DEVICE, compute_type=COMPUTE)
    sys.stderr.write("[karl-whisper] modèle chaud\n")
    sys.stderr.flush()


def _transcribe(audio_path: str, lang):
    """Transcription sérialisée. vad_filter réduit les hallucinations sur les
    silences (typique d'une dictée courte). Renvoie (texte, langue, durée)."""
    with _LOCK:
        segments, info = _MODEL.transcribe(
            audio_path, language=lang or None, beam_size=5, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
    return text, info.language, float(info.duration)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencieux (journald capte stderr)
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path == "/health":
            return self._json(200, {"ok": True, "model": MODEL, "device": DEVICE,
                                    "compute": COMPUTE, "warm": _MODEL is not None})
        return self._json(404, {"error": "route inconnue"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/stt":
            return self._json(404, {"error": "route inconnue"})
        if _MODEL is None:
            return self._json(503, {"error": "modèle non chargé"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return self._json(400, {"error": "audio vide"})
        if n > MAX_BYTES:
            return self._json(413, {"error": f"audio trop volumineux (> {MAX_BYTES // (1024*1024)} Mo)"})
        data = self.rfile.read(n)
        qs = parse_qs(parsed.query)
        lang = (qs.get("lang", [None])[0] or DEFAULT_LANG)
        tf = tempfile.NamedTemporaryFile(prefix="karl-stt-", suffix=".bin", delete=False)
        tmp = tf.name
        tf.write(data)
        tf.close()
        try:
            text, detected, dur = _transcribe(tmp, lang)
            return self._json(200, {"text": text, "lang": detected, "duration": dur})
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"[karl-whisper] échec STT : {type(e).__name__}: {e}\n")
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def main():
    _load_model()  # bloque le démarrage tant que le modèle n'est pas chaud
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    sys.stderr.write(f"[karl-whisper] écoute sur 127.0.0.1:{PORT}\n")
    sys.stderr.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
