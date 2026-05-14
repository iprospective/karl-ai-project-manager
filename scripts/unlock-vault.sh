#!/usr/bin/env bash
# unlock-vault.sh — start vault-agentd (if needed) and feed it BW_SESSION.
#
# Prompts for the karl@iprospective.fr master password (read -s, never logged or written
# to disk). Calls `bw unlock --raw` to obtain a session token, then passes it to the
# in-memory daemon over the Unix socket.
#
# Once unlocked, agents can call resolve-secret.sh which talks to the daemon.
# The daemon keeps the session in memory only — no file. Lock with lock-vault.sh.
#
# Required env (in shell or .env sourced) :
#   BW_CLIENTID       — karl's Vaultwarden API client_id
#   BW_CLIENTSECRET   — karl's Vaultwarden API client_secret
#   VAULT_URL         — e.g. https://vault.iprospective.fr   (default: https://vault.iprospective.fr)
#
# Optional :
#   VAULT_IDLE_TIMEOUT   — seconds of inactivity before auto-lock (default 28800 = 8h)
#   VAULT_LOCK_AT_HOUR   — hour 0-23 for daily auto-lock (default 23 ; -1 to disable)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOCK="/run/user/$(id -u)/vault-agentd.sock"

# Try to source .env from the PM repo root (one dir up from scripts/)
if [ -f "$SCRIPT_DIR/../.env" ]; then
  set -a; . "$SCRIPT_DIR/../.env"; set +a
fi

: "${BW_CLIENTID:?missing — set in .env or env}"
: "${BW_CLIENTSECRET:?missing — set in .env or env}"
: "${VAULT_URL:=https://vault.iprospective.fr}"

if ! command -v bw >/dev/null 2>&1; then
  echo "ERROR: bw (Bitwarden CLI) is not installed. Install : npm i -g @bitwarden/cli" >&2
  exit 1
fi

# Ensure CLI talks to your Vaultwarden instance
bw config server "$VAULT_URL" >/dev/null

# Log in with API key (idempotent — bw status reports if already logged in)
status_json="$(bw status 2>/dev/null || echo '{"status":"unauthenticated"}')"
status="$(printf '%s' "$status_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' 2>/dev/null || echo unauthenticated)"
if [ "$status" = "unauthenticated" ]; then
  echo "Logging in with API key…" >&2
  BW_CLIENTID="$BW_CLIENTID" BW_CLIENTSECRET="$BW_CLIENTSECRET" bw login --apikey >/dev/null
fi

# Start the daemon if not running
if [ ! -S "$SOCK" ] || ! printf 'PING\n' | nc -q1 -U "$SOCK" 2>/dev/null | grep -q '^OK'; then
  echo "Starting vault-agentd…" >&2
  IDLE_OPT=()
  HOUR_OPT=()
  [ -n "${VAULT_IDLE_TIMEOUT:-}" ] && IDLE_OPT=(--idle-timeout "$VAULT_IDLE_TIMEOUT")
  [ -n "${VAULT_LOCK_AT_HOUR:-}" ] && HOUR_OPT=(--lock-at-hour "$VAULT_LOCK_AT_HOUR")
  nohup python3 "$SCRIPT_DIR/vault-agentd.py" "${IDLE_OPT[@]}" "${HOUR_OPT[@]}" </dev/null >/tmp/vault-agentd.log 2>&1 &
  disown || true
  # Wait up to 2s for socket
  for _ in $(seq 1 20); do
    [ -S "$SOCK" ] && break
    sleep 0.1
  done
fi

# Prompt master password (never echoed, never written)
read -r -s -p "Master password for karl@: " MASTER_PWD
echo
[ -z "$MASTER_PWD" ] && { echo "Empty password, aborting." >&2; exit 1; }

# Unlock and obtain session
SESSION="$(BW_SESSION='' bw unlock --raw "$MASTER_PWD" 2>/dev/null || true)"
# Wipe master password from memory ASAP
MASTER_PWD=""
unset MASTER_PWD

if [ -z "$SESSION" ]; then
  echo "Unlock failed (wrong password ?)" >&2
  exit 1
fi

# Hand session to daemon
RESP="$(printf 'SET-SESSION %s\n' "$SESSION" | nc -q1 -U "$SOCK")"
SESSION=""; unset SESSION
if [ "$RESP" != "OK" ]; then
  echo "Daemon did not accept session : $RESP" >&2
  exit 1
fi

STATUS="$(printf 'STATUS\n' | nc -q1 -U "$SOCK")"
echo "✓ Vault unlocked. ${STATUS}"
