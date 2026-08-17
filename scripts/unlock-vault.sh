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
set -uo pipefail
# (no -e : on veut voir explicitement tout échec, pas mourir en silence)
trap 'echo "✗ Script error at line $LINENO (exit $?)" >&2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOCK="/run/user/$(id -u)/vault-agentd.sock"

# Source la config PM depuis la racine du repo (un cran au-dessus de scripts/).
# Scission RM2438 T1 : pm.env (non-secret, ex. VAULT_URL) + .env (secrets, BW_*) →
# sourcer les DEUX (BW_CLIENTID/SECRET sont dans .env, VAULT_URL dans pm.env).
for f in pm.env .env; do
  [ -f "$SCRIPT_DIR/../$f" ] && { set -a; . "$SCRIPT_DIR/../$f"; set +a; }
done

: "${BW_CLIENTID:?missing — set in .env or env}"
: "${BW_CLIENTSECRET:?missing — set in .env or env}"
: "${VAULT_URL:=https://vault.iprospective.fr}"

if ! command -v bw >/dev/null 2>&1; then
  echo "ERROR: bw (Bitwarden CLI) is not installed. Install : npm i -g @bitwarden/cli" >&2
  exit 1
fi

# Log in with API key if needed (bw config server is only allowed when not logged in)
status_json="$(bw status 2>/dev/null || echo '{"status":"unauthenticated"}')"
status="$(printf '%s' "$status_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' 2>/dev/null || echo unauthenticated)"
if [ "$status" = "unauthenticated" ]; then
  bw config server "$VAULT_URL" >/dev/null
  echo "Logging in with API key…" >&2
  BW_CLIENTID="$BW_CLIENTID" BW_CLIENTSECRET="$BW_CLIENTSECRET" bw login --apikey >/dev/null
fi

# Start the daemon if not running
if [ ! -S "$SOCK" ] || ! printf 'PING\n' | nc -N -U "$SOCK" 2>/dev/null | grep -q '^OK'; then
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

# Unlock via --passwordenv (le mdp passe par une env var temporaire, jamais en arg de `ps`)
echo "» calling bw unlock…" >&2
export _VAULT_PWD="$MASTER_PWD"
MASTER_PWD=""; unset MASTER_PWD

SESSION_AND_ERR="$(BW_SESSION='' bw unlock --raw --passwordenv _VAULT_PWD 2>&1)"
RC=$?
unset _VAULT_PWD

echo "» bw unlock exit=$RC, output length=${#SESSION_AND_ERR}" >&2
if [ $RC -ne 0 ] || [ -z "$SESSION_AND_ERR" ]; then
  echo "✗ Unlock failed (exit $RC). bw output :" >&2
  echo "$SESSION_AND_ERR" >&2
  exit 1
fi

# Heuristique : un BW_SESSION est une grosse base64 (>= 40 chars sans espace). Si c'est plus court ou contient un space, c'est probablement un message d'erreur, pas une session.
if [ ${#SESSION_AND_ERR} -lt 40 ] || printf '%s' "$SESSION_AND_ERR" | grep -q ' '; then
  echo "✗ bw output ne ressemble pas à un BW_SESSION token. Reçu :" >&2
  echo "$SESSION_AND_ERR" >&2
  exit 1
fi

SESSION="$SESSION_AND_ERR"
SESSION_AND_ERR=""; unset SESSION_AND_ERR

# Sync vault local cache (login API key ne sync pas automatiquement)
echo "» syncing vault…" >&2
SYNC_OUT="$(BW_SESSION="$SESSION" bw sync 2>&1)"
SYNC_RC=$?
if [ $SYNC_RC -ne 0 ]; then
  echo "⚠ bw sync exit=$SYNC_RC : $SYNC_OUT" >&2
  # not fatal, continue
fi

# Hand session to daemon
echo "» sending SET-SESSION to daemon…" >&2
RESP="$(printf 'SET-SESSION %s\n' "$SESSION" | nc -N -U "$SOCK")"
SESSION=""; unset SESSION
echo "» daemon response: $RESP" >&2
if [ "$RESP" != "OK" ]; then
  echo "✗ Daemon did not accept session : $RESP" >&2
  exit 1
fi

STATUS="$(printf 'STATUS\n' | nc -N -U "$SOCK")"
echo "✓ Vault unlocked. ${STATUS}"
