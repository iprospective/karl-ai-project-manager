#!/usr/bin/env bash
# resolve-secret.sh — fetch a secret from the in-memory vault-agentd.
#
# Usage :
#   resolve-secret.sh "<uri>" [field]
#
# URI forms (RM2681/L0) :
#   secret://<instance>/<path…>[#field]   named vault instance
#   secret:<path…>[#field]                default instance
#   vaultwarden://<org>/<collection>/<item>   legacy form, supported for good
#
# Field defaults to "password" (or the full item JSON if no password set).
# Common fields : password | username | notes | uri | <custom-field-name>
# An explicit [field] argument wins over the URI's `#field`.
#
# Exit codes :
#   0  → secret printed to stdout (no trailing newline besides the one the backend returned)
#   2  → vault is locked → ask the human to run unlock-vault.sh
#   3  → daemon not reachable
#   4  → other error (bad URI, unknown instance, item not found, backend unreachable)
#
# This script never persists the resolved value. The caller is responsible for using it
# safely (e.g. piping into env vars of a subshell, never logging).
set -euo pipefail

# VAULT_SOCK : override du socket (défaut inchangé), utilisé par le harnais de test.
SOCK="${VAULT_SOCK:-/run/user/$(id -u)/vault-agentd.sock}"

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <secret://<instance>/<path> | secret:<path> | vaultwarden://<org>/<col>/<item>> [field]" >&2
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

RESP="$(printf '%s\n' "$CMD" | nc -N -U "$SOCK")"
case "$RESP" in
  "ERR locked"*)
    echo "ERR: vault locked. Lance unlock-vault.sh pour déverrouiller." >&2
    exit 2
    ;;
  "ERR unreachable"*)
    # Backend déclaré mais hors d'atteinte : CLI absente, fichier manquant, réseau muet.
    echo "$RESP" >&2
    exit 4
    ;;
  "ERR "*)
    echo "$RESP" >&2
    exit 4
    ;;
  *)
    printf '%s\n' "$RESP"
    ;;
esac
