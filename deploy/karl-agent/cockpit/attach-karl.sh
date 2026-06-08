#!/usr/bin/env bash
# Wrapper d'attach pour ttyd — cockpit karl-agent (RM1873).
#
# ttyd est lancé avec `-a` (le client peut passer des arguments via l'URL :
# http://…:7681/?arg=<rm_id>). ttyd exécute alors `attach-karl.sh <rm_id>`.
# On VALIDE STRICTEMENT cet argument pour qu'aucune chaîne arbitraire n'atteigne
# tmux, puis on attache la session `karl-RM<id>` en lecture/écriture (ttyd -W),
# ce qui donne la reprise de main humaine depuis le navigateur.
#
# Codes de sortie : 2 = rm_id invalide, 3 = session absente.
set -euo pipefail

id="${1:-}"
if ! [[ "$id" =~ ^[0-9]+$ ]]; then
  echo "rm_id invalide : '$id' (attendu ^[0-9]+\$)" >&2
  exit 2
fi

session="karl-RM${id}"
if ! tmux has-session -t "$session" 2>/dev/null; then
  echo "session absente : $session" >&2
  echo "(lance-la d'abord depuis le cockpit, ou via POST /spawn)" >&2
  exit 3
fi

exec tmux attach -t "$session"
