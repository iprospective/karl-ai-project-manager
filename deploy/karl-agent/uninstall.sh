#!/usr/bin/env bash
# Désinstalle karl-agent + son tunnel (services systemd USER) du LXC `dev`.
# Idempotent (ne hurle pas si déjà absent). Symétrique de install.sh.
# À lancer EN TANT QUE mathieu DANS le conteneur `dev`.
#
# Options :
#   --kill-sessions    tue aussi les sessions tmux `karl-RM*` encore vivantes
#                      (par défaut on les laisse : un humain peut être attaché).
#   --disable-linger   désactive le linger de l'utilisateur (par défaut NON :
#                      d'autres services user peuvent en dépendre).
set -euo pipefail

UNIT_DST="$HOME/.config/systemd/user"
KILL_SESSIONS=0
DISABLE_LINGER=0
for arg in "$@"; do
  case "$arg" in
    --kill-sessions)  KILL_SESSIONS=1 ;;
    --disable-linger) DISABLE_LINGER=1 ;;
    *) echo "option inconnue : $arg" >&2; exit 2 ;;
  esac
done

echo "==> Arrêt + désactivation des services"
for svc in karl-agent.service karl-agent-tunnel.service; do
  systemctl --user disable --now "$svc" 2>/dev/null || true
done

echo "==> Suppression des units dans $UNIT_DST"
rm -f "$UNIT_DST/karl-agent.service" "$UNIT_DST/karl-agent-tunnel.service"
systemctl --user daemon-reload
systemctl --user reset-failed karl-agent.service karl-agent-tunnel.service 2>/dev/null || true

if [ "$KILL_SESSIONS" = 1 ]; then
  echo "==> Fermeture des sessions tmux karl-RM*"
  if command -v tmux >/dev/null 2>&1; then
    tmux list-sessions -F '#{session_name}' 2>/dev/null \
      | grep '^karl-RM' \
      | while read -r s; do echo "  kill $s"; tmux kill-session -t "$s" 2>/dev/null || true; done
  fi
else
  echo "==> Sessions tmux karl-RM* conservées (relance avec --kill-sessions pour les fermer)"
fi

if [ "$DISABLE_LINGER" = 1 ]; then
  echo "==> Désactivation du linger"
  loginctl disable-linger "$USER" || echo "  (disable-linger a échoué — peut nécessiter root)"
else
  echo "==> Linger conservé (relance avec --disable-linger pour le retirer)"
fi

echo
echo "OK. karl-agent désinstallé."
echo "Note : le code (scripts/, deploy/) et les logs (~/.local/state/karl-agent/) sont conservés."
