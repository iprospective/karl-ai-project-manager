#!/usr/bin/env bash
# karl-voice-setup — installe le TTS serveur Piper pour le cockpit (RM2532, vocal V2 L1).
# Idempotent, SANS root : venv utilisateur + modèles fr/en dans le runtime karl-agent.
# karl-agent détecte automatiquement (op_voice_caps) ; absent → repli synthèse navigateur.
#
#   bash scripts/karl-voice-setup.sh
#
# Puis : systemctl --user restart karl-agent  (pour re-sonder les capacités).
set -euo pipefail

VOICE_DIR="${KARL_VOICE_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/karl-agent/voice}"
VENV="$VOICE_DIR/venv"
MODELS="$VOICE_DIR/models"
HF="https://huggingface.co/rhasspy/piper-voices/resolve/main"

# modèles par défaut (nom PRÉFIXÉ par la langue : fr_… / en_… — requis par _piper_models)
FR="fr/fr_FR/siwis/medium/fr_FR-siwis-medium"
EN="en/en_US/lessac/medium/en_US-lessac-medium"

echo "==> Runtime voix : $VOICE_DIR"
mkdir -p "$MODELS"

echo "==> venv Piper (piper-tts)"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip >/dev/null
"$VENV/bin/pip" install -q piper-tts
"$VENV/bin/piper" --help >/dev/null 2>&1 && echo "  piper OK ($("$VENV/bin/piper" --version 2>/dev/null || echo installé))"

fetch_model() {
  local rel="$1" base name
  name="$(basename "$rel")"                 # fr_FR-siwis-medium
  for ext in onnx onnx.json; do
    if [ -s "$MODELS/$name.$ext" ]; then
      echo "  $name.$ext déjà présent"
    else
      echo "  téléchargement $name.$ext…"
      curl -fsSL "$HF/$rel.$ext" -o "$MODELS/$name.$ext"
    fi
  done
}

echo "==> Modèles (fr, en)"
fetch_model "$FR"
fetch_model "$EN"

# ── STT — sidecar Whisper (RM2533, vocal V2 L2) ──────────────────────────────
# faster-whisper dans LE MÊME venv + unité systemd user karl-whisper (modèle chaud).
# Absent → /voice/caps annonce stt:false et le cockpit reste sur la Web Speech API.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
UNIT_DST="$HOME/.config/systemd/user"
WHISPER_MODEL="${KARL_WHISPER_MODEL:-small}"

echo "==> STT : faster-whisper (venv partagé)"
"$VENV/bin/pip" install -q faster-whisper

echo "==> STT : préchauffe du modèle « $WHISPER_MODEL » (download au 1er coup, ~0,5 Go RAM à l'usage)"
"$VENV/bin/python" - "$WHISPER_MODEL" <<'PY' || echo "  (préchauffe non bloquante ignorée)"
import sys
from faster_whisper import WhisperModel
WhisperModel(sys.argv[1], device="cpu", compute_type="int8")   # download + cache HF
print("  modèle prêt")
PY

if [ -f "$REPO/deploy/karl-agent/karl-whisper.service" ]; then
  echo "==> STT : unité systemd user karl-whisper"
  mkdir -p "$UNIT_DST"
  cp "$REPO/deploy/karl-agent/karl-whisper.service" "$UNIT_DST/"
  systemctl --user daemon-reload
  systemctl --user enable --now karl-whisper.service || true
fi

echo
echo "OK — voix serveur installée."
echo "  TTS (Piper) :"
ls -1 "$MODELS"/*.onnx 2>/dev/null | sed 's#.*/#    #'
echo "  STT (Whisper) : sidecar karl-whisper.service, modèle $WHISPER_MODEL"
echo
echo "Active/rafraîchit :  systemctl --user restart karl-agent"
echo "Vérifie          :  curl -s http://127.0.0.1:9876/voice/caps  (avec auth)"
echo "                    → {\"tts\": true, \"stt\": true, \"stt_engine\": \"whisper\", ...}"
echo "Sidecar STT      :  systemctl --user status karl-whisper   ·   curl -s http://127.0.0.1:9877/health"
