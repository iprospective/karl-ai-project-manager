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

echo
echo "OK — TTS serveur installé. Modèles :"
ls -1 "$MODELS"/*.onnx 2>/dev/null | sed 's#.*/#  #'
echo
echo "Active-le :  systemctl --user restart karl-agent"
echo "Vérifie   :  curl -s http://127.0.0.1:9876/voice/caps   (avec auth) → {\"tts\": true, ...}"
