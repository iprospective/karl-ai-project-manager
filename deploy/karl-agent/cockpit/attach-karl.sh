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
# RM2144 : sid = id de ticket (idéal → karl-RM<id>) OU slug (→ karl-<slug>).
# Validation stricte inchangée dans l'esprit : rien d'arbitraire n'atteint tmux.
if [[ "$id" =~ ^[0-9]+$ ]]; then
  session="karl-RM${id}"
elif [[ "$id" =~ ^[a-z0-9][a-z0-9_-]{1,40}$ ]] && ! [[ "$id" =~ ^rm[0-9]+$ ]]; then
  session="karl-${id}"
else
  echo "sid invalide : '$id' (attendu ^[0-9]+\$ ou slug ^[a-z0-9][a-z0-9_-]{1,40}\$)" >&2
  exit 2
fi
if ! tmux has-session -t "$session" 2>/dev/null; then
  echo "session absente : $session" >&2
  echo "(lance-la d'abord depuis le cockpit, ou via POST /spawn)" >&2
  exit 3
fi

exec tmux attach -t "$session"
