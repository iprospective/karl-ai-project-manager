#!/usr/bin/env bash
# vault-list.sh — list items visible to the unlocked vault-agentd.
#
# Usage :
#   vault-list.sh                  # tous les items visibles
#   vault-list.sh <substring>      # filtre par sous-chaîne dans le nom
#
# Output : un item par ligne, format `<uuid>\t<org_id>\t<collection_ids>\t<name>`
set -uo pipefail

SOCK="/run/user/$(id -u)/vault-agentd.sock"

if [ ! -S "$SOCK" ]; then
  echo "ERR: vault-agentd not running. Lance unlock-vault.sh." >&2
  exit 3
fi

CMD="LIST"
[ "$#" -ge 1 ] && CMD="LIST $1"

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
