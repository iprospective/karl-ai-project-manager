#!/usr/bin/env bash
# Installe karl-agent + son tunnel comme services systemd USER sur le LXC `dev`.
# Idempotent. À lancer EN TANT QUE mathieu DANS le conteneur `dev` (pas en root,
# pas sur l'host) : ssh mathieu@dev.lxc puis exécuter ce script.
#
# Prérequis (vérifiés ci-dessous) : python3, tmux, autossh, et un moteur d'agent
# (claude ou opencode) dans le PATH ; alias SSH `mmi` joignable depuis `dev`.
set -euo pipefail

REPO="/zfs/workspaces/ai/project-management"
UNIT_SRC="$REPO/deploy/karl-agent"
UNIT_DST="$HOME/.config/systemd/user"

echo "==> Vérification des prérequis"
need() { command -v "$1" >/dev/null 2>&1 || { echo "  MANQUANT : $1"; MISSING=1; }; }
MISSING=0
need python3
need tmux
need autossh
command -v claude >/dev/null 2>&1 || command -v opencode >/dev/null 2>&1 || {
  echo "  MANQUANT : moteur d'agent (claude ou opencode)"; MISSING=1; }
if [ "$MISSING" = 1 ]; then
  echo "Installe les paquets manquants puis relance. (ex : sudo apt install tmux autossh)"
  exit 1
fi

echo "==> Test de l'alias SSH 'mmi' (tunnel)"
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 mmi true 2>/dev/null; then
  echo "  ATTENTION : 'ssh mmi' ne répond pas en BatchMode. Vérifie ~/.ssh/config"
  echo "  et la clé autorisée côté mmi avant d'activer karl-agent-tunnel.service."
fi

echo "==> Installation des units dans $UNIT_DST"
mkdir -p "$UNIT_DST"
cp "$UNIT_SRC/karl-agent.service"        "$UNIT_DST/"
cp "$UNIT_SRC/karl-agent-tunnel.service" "$UNIT_DST/"
systemctl --user daemon-reload

echo "==> Activation du linger (survie aux reboots sans session ouverte)"
if ! loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
  loginctl enable-linger "$USER" || echo "  (enable-linger a échoué — peut nécessiter root une fois)"
fi

echo "==> Activation + démarrage des services"
systemctl --user enable --now karl-agent.service
systemctl --user enable --now karl-agent-tunnel.service

echo "==> État"
systemctl --user --no-pager status karl-agent.service karl-agent-tunnel.service || true
echo
echo "OK. Test local :   curl -s http://127.0.0.1:9876/health"
echo "Test depuis mmi :  ssh mmi 'curl -s http://127.0.0.1:9876/health'"
