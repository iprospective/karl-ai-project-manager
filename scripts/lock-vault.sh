#!/usr/bin/env bash
# lock-vault.sh — tell vault-agentd to wipe a session (or all of them) and exit.
#
# Usage :
#   lock-vault.sh                # verrouille TOUTES les instances, le daemon quitte
#   lock-vault.sh <instance>     # verrouille cette instance seulement (RM2683)
#
# Le daemon ne quitte que lorsqu'il ne reste plus aucune instance déverrouillée.
set -euo pipefail

SOCK="${VAULT_SOCK:-/run/user/$(id -u)/vault-agentd.sock}"
INSTANCE="${1:-}"

if [ ! -S "$SOCK" ]; then
  echo "vault-agentd is not running."
  exit 0
fi

CMD="LOCK"
[ -n "$INSTANCE" ] && CMD="LOCK $INSTANCE"

RESP="$(printf '%s\n' "$CMD" | nc -N -U "$SOCK" 2>/dev/null || true)"
if [ "$RESP" = "OK" ]; then
  if [ -n "$INSTANCE" ]; then
    echo "✓ Vault « $INSTANCE » locked."
  else
    echo "✓ Vault locked (toutes les instances)."
  fi
else
  echo "Lock response : $RESP" >&2
fi
