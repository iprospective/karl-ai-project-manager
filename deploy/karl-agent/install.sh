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

# ttyd est OPTIONNEL : il alimente le terminal web du cockpit (RM1873). Son
# absence n'empêche pas karl-agent ni la page cockpit de tourner (seul l'attach
# navigateur est indisponible). On ne bloque donc pas dessus.
HAVE_TTYD=0
if command -v ttyd >/dev/null 2>&1; then HAVE_TTYD=1; else
  echo "  (optionnel) ttyd absent — le cockpit web fonctionnera sauf l'attach"
  echo "             navigateur. Pour l'activer : sudo apt install ttyd"
fi

# PIÈGE CONNU (vécu sur dev, RM1873) : le paquet `ttyd` (apt) installe ET active
# tout seul un service SYSTÈME `ttyd.service` qui lance `ttyd -p 7681 -O login`
# (un login web) → il squatte le port 7681 et NOTRE ttyd user (qui fait
# `attach-karl.sh`) ne peut plus binder (EADDRINUSE, crash-loop). Symptôme dans
# le navigateur : un prompt « <host> login: » au lieu du TUI de l'agent.
# `systemctl is-enabled/is-active` SANS --user interroge le manager système :
# il voit le service du paquet, pas le nôtre (homonyme, scope user).
if systemctl is-enabled ttyd.service >/dev/null 2>&1 || systemctl is-active ttyd.service >/dev/null 2>&1; then
  echo "  ⚠ Le service SYSTÈME ttyd.service (paquet apt) occupe le port 7681."
  echo "    Neutralise-le (root) AVANT que notre ttyd user puisse démarrer :"
  echo "      sudo systemctl disable --now ttyd.service && sudo systemctl mask ttyd.service"
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
cp "$UNIT_SRC/ttyd.service"              "$UNIT_DST/"
systemctl --user daemon-reload

echo "==> Activation du linger (survie aux reboots sans session ouverte)"
if ! loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
  loginctl enable-linger "$USER" || echo "  (enable-linger a échoué — peut nécessiter root une fois)"
fi

echo "==> Activation + démarrage des services"
systemctl --user enable --now karl-agent.service
systemctl --user enable --now karl-agent-tunnel.service
if [ "$HAVE_TTYD" = 1 ]; then
  systemctl --user enable --now ttyd.service
else
  echo "  ttyd absent : ttyd.service installé mais NON démarré."
  echo "  Après 'sudo apt install ttyd' : systemctl --user enable --now ttyd.service"
fi

echo "==> État"
systemctl --user --no-pager status karl-agent.service karl-agent-tunnel.service || true
[ "$HAVE_TTYD" = 1 ] && systemctl --user --no-pager status ttyd.service || true
echo
echo "OK. Test local :   curl -s http://127.0.0.1:9876/health"
echo "Test depuis mmi :  ssh mmi 'curl -s http://127.0.0.1:9876/health'"
echo
echo "Cockpit web (LOCAL uniquement tant que l'auth RM1845 n'est pas en place) :"
echo "  depuis le laptop :  ssh -L 9876:localhost:9876 -L 7681:localhost:7681 dev.lxc"
echo "  puis navigateur :   http://localhost:9876/"
