#!/usr/bin/env bash
# lock-vault.sh — tell vault-agentd to wipe its session and exit.
set -euo pipefail

SOCK="/run/user/$(id -u)/vault-agentd.sock"

if [ ! -S "$SOCK" ]; then
  echo "vault-agentd is not running."
  exit 0
fi

RESP="$(printf 'LOCK\n' | nc -q1 -U "$SOCK" 2>/dev/null || true)"
if [ "$RESP" = "OK" ]; then
  echo "✓ Vault locked."
else
  echo "Lock response : $RESP" >&2
fi
