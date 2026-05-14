#!/usr/bin/env bash
# resolve-secret.sh — fetch a secret from the in-memory vault-agentd.
#
# Usage :
#   resolve-secret.sh "vaultwarden://<org>/<collection>/<item>" [field]
#
# Field defaults to "password" (or the full item JSON if no password set).
# Common fields : password | username | notes | uri | <custom-field-name>
#
# Exit codes :
#   0  → secret printed to stdout (no trailing newline besides the one bw returned)
#   2  → vault is locked → ask the human to run unlock-vault.sh
#   3  → daemon not reachable
#   4  → other error
#
# This script never persists the resolved value. The caller is responsible for using it
# safely (e.g. piping into env vars of a subshell, never logging).
set -euo pipefail

SOCK="/run/user/$(id -u)/vault-agentd.sock"

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 vaultwarden://<org>/<col>/<item> [field]" >&2
  exit 4
fi
URI="$1"
FIELD="${2:-}"

if [ ! -S "$SOCK" ]; then
  echo "ERR: vault-agentd not running. Lance unlock-vault.sh." >&2
  exit 3
fi

CMD="GET $URI"
[ -n "$FIELD" ] && CMD="GET $URI $FIELD"

RESP="$(printf '%s\n' "$CMD" | nc -q1 -U "$SOCK")"
case "$RESP" in
  "ERR locked"*)
    echo "ERR: vault locked. Lance unlock-vault.sh pour saisir le master password." >&2
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
