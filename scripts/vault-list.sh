#!/usr/bin/env bash
# vault-list.sh — list items visible to the unlocked vault-agentd.
#
# Usage :
#   vault-list.sh                        # items de l'instance par défaut
#   vault-list.sh <substring>            # filtre par sous-chaîne dans le nom
#   vault-list.sh -i <instance> [filtre] # items d'une instance nommée (RM2683)
#
# Output : un item par ligne, format `<uuid>\t<org_id>\t<collection_ids>\t<name>`
set -uo pipefail

SOCK="${VAULT_SOCK:-/run/user/$(id -u)/vault-agentd.sock}"

INSTANCE=""
if [ "${1:-}" = "-i" ]; then
  [ "$#" -ge 2 ] || { echo "Usage: $0 -i <instance> [filtre]" >&2; exit 4; }
  INSTANCE="$2"; shift 2
fi

if [ ! -S "$SOCK" ]; then
  echo "ERR: vault-agentd not running. Lance unlock-vault.sh." >&2
  exit 3
fi

if [ -n "$INSTANCE" ]; then
  CMD="LIST-IN $INSTANCE"
  [ "$#" -ge 1 ] && CMD="LIST-IN $INSTANCE $1"
else
  CMD="LIST"
  [ "$#" -ge 1 ] && CMD="LIST $1"
fi

RESP="$(printf '%s\n' "$CMD" | nc -N -U "$SOCK")"
case "$RESP" in
  "ERR locked"*)
    echo "ERR: vault locked. Lance unlock-vault.sh." >&2
    exit 2
    ;;
  "ERR "*)
    echo "$RESP" >&2
    exit 4
    ;;
  *)
    printf '%s\n' "$RESP"
    ;;
esac
