#!/usr/bin/env bash
# unlock-vault.sh — start vault-agentd (if needed) and feed it BW_SESSION.
#
# Usage :
#   unlock-vault.sh                  # instance par défaut (VAULT_INSTANCE, défaut vw-ipro)
#   unlock-vault.sh -i <instance>    # une instance Vaultwarden nommée (RM2683)
#   unlock-vault.sh --stdin          # mot de passe lu sur l'entrée standard (RM2748),
#                                    # sans invite : appelants non interactifs (cockpit)
#
# Chaque instance a sa propre session côté daemon : déverrouiller le vault d'un
# client ne prolonge pas celui d'iProspective. Les identifiants d'API sont pris
# par instance (`SECRET__<slug>__CLIENTID` / `__CLIENTSECRET`, RM2682) avec repli
# sur BW_CLIENTID / BW_CLIENTSECRET.
#
# Chaque type de backend a sa sémantique : `vaultwarden` (mot de passe maître +
# `bw`), `keepass` (passphrase poussée au daemon, RM2684), `age` (rien à
# déverrouiller — la clé est un fichier, RM2713), `nextcloud_passwords` (rien à
# déverrouiller non plus — un mot de passe d'application, RM2712) et
# `onepassword` (rien non plus — un jeton de service account, RM2711).
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
SOCK="${VAULT_SOCK:-/run/user/$(id -u)/vault-agentd.sock}"

INSTANCE="${VAULT_INSTANCE:-vw-ipro}"
# --stdin (RM2748) : le mot de passe arrive sur l'entrée standard, sans invite.
# C'est ce qui permet à un appelant NON INTERACTIF (le cockpit) de déverrouiller
# sans jamais mettre le secret en argument de commande — `ps` le montrerait.
STDIN_PWD=0
while [ $# -gt 0 ]; do
  case "$1" in
    -i)       [ "$#" -ge 2 ] || { echo "Usage: $0 [-i <instance>] [--stdin]" >&2; exit 1; }
              INSTANCE="$2"; shift 2 ;;
    --stdin)  STDIN_PWD=1; shift ;;
    *)        break ;;
  esac
done

# Source la config PM depuis la racine du repo (un cran au-dessus de scripts/).
# Scission RM2438 T1 : pm.env (non-secret, ex. VAULT_URL) + .env (secrets, BW_*) →
# sourcer les DEUX (BW_CLIENTID/SECRET sont dans .env, VAULT_URL dans pm.env).
for f in pm.env .env; do
  [ -f "$SCRIPT_DIR/../$f" ] && { set -a; . "$SCRIPT_DIR/../$f"; set +a; }
done

# Identifiants par instance (RM2682/RM2683), repli sur les variables historiques
# du .env. Le slug est normalisé (majuscules, non-alphanum → `_`) : un nom de
# variable shell n'accepte pas de tiret — `vw-ipro` → `SECRET__VW_IPRO__…`.
SLUG="$(printf '%s' "$INSTANCE" | tr '[:lower:]' '[:upper:]' | tr -c 'A-Z0-9' '_')"

# `_cred <SUFFIXE> <repli>` : valeur par instance si NON VIDE, sinon le repli
# historique. Une variable déclarée vide compte comme absente (piège classique :
# `printenv` réussit sur une variable vide et masquerait le repli).
_cred() {
  local v; v="$(printenv "SECRET__${SLUG}__$1" 2>/dev/null || true)"
  printf '%s' "${v:-$2}"
}
VAULT_FILE="$(_cred FILE "")"       # .kdbx (keepass) ou fichier chiffré (age)
KDBX_FILE="$VAULT_FILE"

# Type du backend, lu dans le registre providers. Inconnu (registre absent) →
# `vaultwarden`, le comportement d'avant le chantier.
TYPE="$(python3 "$SCRIPT_DIR/pm-providers.py" instance "$INSTANCE" --field type 2>/dev/null || true)"
[ -z "$TYPE" ] && TYPE="vaultwarden"

# Identifiants Vaultwarden : le repli sur les variables globales du `.env` ne vaut
# que pour une instance de CE type — sinon un vault KeePass afficherait les clés
# API de Vaultwarden et l'URL du serveur, ce qui n'a aucun sens pour un fichier.
if [ "$TYPE" = "vaultwarden" ]; then
  BW_CLIENTID="$(_cred CLIENTID "${BW_CLIENTID:-}")"
  BW_CLIENTSECRET="$(_cred CLIENTSECRET "${BW_CLIENTSECRET:-}")"
  VAULT_URL="$(_cred URL "${VAULT_URL:-}")"
else
  BW_CLIENTID="$(_cred CLIENTID "")"
  BW_CLIENTSECRET="$(_cred CLIENTSECRET "")"
  VAULT_URL="$(_cred URL "")"
fi

if [ "${1:-}" = "--print-instance" ] || [ "${PRINT_INSTANCE:-}" = "1" ]; then
  # Diagnostic : quelle instance, quelles clés trouvées — jamais les valeurs.
  # Les clés affichées sont celles qui COMPTENT pour le type de l'instance.
  found=""; cible=""
  case "$TYPE" in
    keepass)
      [ -z "$KDBX_FILE" ] && KDBX_FILE="$(python3 "$SCRIPT_DIR/pm-providers.py" instance "$INSTANCE" --field file 2>/dev/null || true)"
      [ -n "$KDBX_FILE" ] && found="$found FILE"
      [ -n "$(_cred KEYFILE "")" ] && found="$found KEYFILE"
      cible="file=${KDBX_FILE:-—}"
      ;;
    age)
      [ -z "$VAULT_FILE" ] && VAULT_FILE="$(python3 "$SCRIPT_DIR/pm-providers.py" instance "$INSTANCE" --field file 2>/dev/null || true)"
      [ -n "$VAULT_FILE" ] && found="$found FILE"
      [ -n "$(_cred AGE_KEY_FILE "")" ] && found="$found AGE_KEY_FILE"
      cible="file=${VAULT_FILE:-—}"
      ;;
    onepassword)
      OP_VAULT="$(_cred VAULT "")"
      [ -z "$OP_VAULT" ] && OP_VAULT="$(python3 "$SCRIPT_DIR/pm-providers.py" instance "$INSTANCE" --field vault 2>/dev/null || true)"
      [ -n "$OP_VAULT" ] && found="$found VAULT"
      [ -n "$(_cred SERVICE_ACCOUNT_TOKEN "")" ] && found="$found SERVICE_ACCOUNT_TOKEN"
      [ -n "$(_cred ACCOUNT "")" ] && found="$found ACCOUNT"
      cible="vault=${OP_VAULT:-—}"
      ;;
    nextcloud_passwords)
      NC_URL="$(_cred URL "")"
      [ -z "$NC_URL" ] && NC_URL="$(python3 "$SCRIPT_DIR/pm-providers.py" instance "$INSTANCE" --field url 2>/dev/null || true)"
      [ -n "$NC_URL" ] && found="$found URL"
      [ -n "$(_cred USER "")" ] && found="$found USER"
      [ -n "$(_cred TOKEN "")" ] && found="$found TOKEN"
      cible="url=${NC_URL:-—}"
      ;;
    *)
      [ -n "$BW_CLIENTID" ] && found="$found CLIENTID"
      [ -n "$BW_CLIENTSECRET" ] && found="$found CLIENTSECRET"
      [ -n "$VAULT_URL" ] && found="$found URL"
      cible="url=${VAULT_URL:-—}"
      ;;
  esac
  echo "instance=$INSTANCE slug=$SLUG type=$TYPE $cible creds=${found:- aucun}"
  exit 0
fi

# ── Démarrage du daemon (commun à tous les types) ───────────────────────────
_start_daemon() {
  if [ ! -S "$SOCK" ] || ! printf 'PING\n' | nc -N -U "$SOCK" 2>/dev/null | grep -q '^OK'; then
    echo "Starting vault-agentd…" >&2
    local IDLE_OPT=() HOUR_OPT=()
    [ -n "${VAULT_IDLE_TIMEOUT:-}" ] && IDLE_OPT=(--idle-timeout "$VAULT_IDLE_TIMEOUT")
    [ -n "${VAULT_LOCK_AT_HOUR:-}" ] && HOUR_OPT=(--lock-at-hour "$VAULT_LOCK_AT_HOUR")
    nohup python3 "$SCRIPT_DIR/vault-agentd.py" "${IDLE_OPT[@]}" "${HOUR_OPT[@]}" \
      </dev/null >/tmp/vault-agentd.log 2>&1 &
    disown || true
    for _ in $(seq 1 20); do [ -S "$SOCK" ] && break; sleep 0.1; done
  fi
}

# ── État réel d'une instance sans déverrouillage (RM2712, RM2711) ───────────
# Le diagnostic passe par le BACKEND lui-même : une seule implémentation de la
# vérification, pas une seconde écrite en shell qui divergerait de la première.
_etat_backend() {
  PM_BACKEND_TYPE="$1" PM_INSTANCE="$INSTANCE" SCRIPT_DIR="$SCRIPT_DIR" python3 -c '
import os, sys
sys.path.insert(0, os.environ["SCRIPT_DIR"])
import pm_secrets
from pm_paths import PMConfig
from pm_registry import Registry
slug = os.environ["PM_INSTANCE"]
reg = Registry.from_config(PMConfig.load(os.environ.get("PM_CORE_DIR") or None).providers)
inst = reg.servers.get(slug)
opts = dict(inst.options) if inst else {}
if inst is not None and getattr(inst, "url", None):
    opts.setdefault("url", inst.url)
b = pm_secrets.get_backend(os.environ["PM_BACKEND_TYPE"], name=slug, **opts)
print(b.status())
' 2>&1 | tail -1
}

# ── 1Password : rien à déverrouiller, le jeton EST la session ───────────────
# Un jeton refusé n'est pas un coffre verrouillé : aucun humain ne peut le
# « déverrouiller ». Le message doit donc envoyer émettre un AUTRE jeton, pas
# faire chercher un mot de passe maître qui n'existe pas ici.
if [ "$TYPE" = "onepassword" ]; then
  echo "ℹ instance « $INSTANCE » (onepassword) : aucun déverrouillage — jeton de service account."
  ETAT="$(_etat_backend onepassword)"
  case "$ETAT" in
    unlocked) echo "✓ instance « $INSTANCE » joignable et jeton accepté." ; exit 0 ;;
    locked)   echo "✗ jeton refusé — émets-en un nouveau depuis 1Password et remplace SECRET__${SLUG}__SERVICE_ACCOUNT_TOKEN." >&2 ; exit 1 ;;
    *)        echo "✗ instance injoignable ou mal configurée : $ETAT" >&2
              command -v op >/dev/null 2>&1 || echo "  (la CLI \`op\` est absente : https://developer.1password.com/docs/cli/get-started/)" >&2
              exit 1 ;;
  esac
fi

# ── Nextcloud Passwords : rien à déverrouiller, l'accès se teste ────────────
# Le mot de passe d'application vit dans le `.env` du dev. Ce que le script peut
# faire d'utile, c'est répondre à « est-ce que ça marche, là, maintenant ? » —
# question à laquelle on ne veut pas découvrir la réponse au milieu d'un déploiement.
if [ "$TYPE" = "nextcloud_passwords" ]; then
  echo "ℹ instance « $INSTANCE » (nextcloud_passwords) : aucun déverrouillage — mot de passe d'application."
  ETAT="$(_etat_backend nextcloud_passwords)"
  case "$ETAT" in
    unlocked) echo "✓ instance « $INSTANCE » joignable et identifiants acceptés." ; exit 0 ;;
    locked)   echo "✗ instance joignable, mais les identifiants sont refusés (SECRET__${SLUG}__USER / __TOKEN)." >&2 ; exit 1 ;;
    *)        echo "✗ instance injoignable ou mal configurée : $ETAT" >&2 ; exit 1 ;;
  esac
fi

# ── age : rien à déverrouiller, mais tout à vérifier ────────────────────────
# La clé est un fichier : il n'y a pas de session à poser. Le script se rend donc
# utile autrement — il dit si l'instance est réellement utilisable, et il alerte
# quand la clé privée est lisible par d'autres que son propriétaire.
if [ "$TYPE" = "age" ]; then
  [ -z "$VAULT_FILE" ] && VAULT_FILE="$(python3 "$SCRIPT_DIR/pm-providers.py" instance "$INSTANCE" --field file 2>/dev/null || true)"
  AGE_KEY="$(_cred AGE_KEY_FILE "")"
  echo "ℹ instance « $INSTANCE » (age) : aucun déverrouillage — la clé est un fichier."
  rc=0
  if [ -z "$VAULT_FILE" ]; then
    echo "✗ aucun fichier chiffré (providers.servers.$INSTANCE.file ou SECRET__${SLUG}__FILE)" >&2; rc=1
  elif [ ! -f "${VAULT_FILE/#\~/$HOME}" ]; then
    echo "✗ fichier chiffré introuvable : $VAULT_FILE" >&2; rc=1
  fi
  if [ -z "$AGE_KEY" ]; then
    echo "✗ aucune clé : renseigne SECRET__${SLUG}__AGE_KEY_FILE dans ton .env" >&2; rc=1
  else
    AGE_KEY_ABS="${AGE_KEY/#\~/$HOME}"
    if [ ! -f "$AGE_KEY_ABS" ]; then
      echo "✗ clé age introuvable : $AGE_KEY" >&2; rc=1
    else
      MODE="$(stat -c '%a' "$AGE_KEY_ABS" 2>/dev/null || echo '?')"
      case "$MODE" in
        600|400) ;;
        *) echo "⚠ clé $AGE_KEY en mode $MODE : elle est lisible au-delà de toi — \`chmod 600\`" >&2 ;;
      esac
    fi
  fi
  command -v age >/dev/null 2>&1 || { echo "✗ binaire \`age\` absent — sudo apt install age" >&2; rc=1; }
  [ $rc -eq 0 ] && echo "✓ instance « $INSTANCE » utilisable (file=$VAULT_FILE)."
  exit $rc
fi

# ── KeePass : pas de `bw`, juste une passphrase poussée au daemon ────────────
# Même discipline que pour le mot de passe maître : saisie non echo, jamais
# écrite sur disque, jamais en argument de commande visible dans `ps`.
if [ "$TYPE" = "keepass" ]; then
  if [ -z "$KDBX_FILE" ]; then
    KDBX_FILE="$(python3 "$SCRIPT_DIR/pm-providers.py" instance "$INSTANCE" --field file 2>/dev/null || true)"
  fi
  [ -n "$KDBX_FILE" ] || {
    echo "✗ instance $INSTANCE : aucun fichier .kdbx (providers.servers.$INSTANCE.file ou SECRET__${SLUG}__FILE)" >&2
    exit 1; }
  _start_daemon
  if [ "$STDIN_PWD" = "1" ]; then
    IFS= read -r KP_PWD || true
  else
    read -r -s -p "Passphrase KeePass ($INSTANCE) : " KP_PWD
    echo
  fi
  [ -z "$KP_PWD" ] && { echo "Passphrase vide, abandon." >&2; exit 1; }
  RESP="$(printf 'SET-SESSION %s %s\n' "$INSTANCE" "$KP_PWD" | nc -N -U "$SOCK")"
  KP_PWD=""; unset KP_PWD
  if [ "$RESP" != "OK" ]; then
    echo "✗ Daemon did not accept session : $RESP" >&2
    exit 1
  fi
  # Vérifie tout de suite que la passphrase ouvre bien la base : sans ça, l'échec
  # ne se verrait qu'à la première résolution, longtemps après la saisie.
  CHECK="$(printf 'LIST-IN %s\n' "$INSTANCE" | nc -N -U "$SOCK")"
  case "$CHECK" in
    "ERR denied"*)
      printf 'LOCK %s\n' "$INSTANCE" | nc -N -U "$SOCK" >/dev/null
      echo "✗ Passphrase refusée par la base $KDBX_FILE." >&2; exit 1 ;;
    "ERR "*)
      echo "⚠ Session posée, mais la base n'a pas répondu : $CHECK" >&2 ;;
  esac
  echo "✓ KeePass « $INSTANCE » unlocked ($KDBX_FILE)."
  exit 0
fi

# ── Vaultwarden / Bitwarden (flux historique) ───────────────────────────────

: "${BW_CLIENTID:?missing — set SECRET__${SLUG}__CLIENTID (ou BW_CLIENTID)}"
: "${BW_CLIENTSECRET:?missing — set SECRET__${SLUG}__CLIENTSECRET (ou BW_CLIENTSECRET)}"
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

# Start the daemon if not running (même helper que la branche KeePass)
_start_daemon

# Prompt master password (never echoed, never written)
if [ "$STDIN_PWD" = "1" ]; then
  IFS= read -r MASTER_PWD || true
else
  read -r -s -p "Master password for karl@: " MASTER_PWD
  echo
fi
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
# Le slug est explicite : sans lui, un `-i <autre-instance>` poserait la session
# sur l'instance PAR DÉFAUT — le bon token dans le mauvais coffre.
RESP="$(printf 'SET-SESSION %s %s\n' "$INSTANCE" "$SESSION" | nc -N -U "$SOCK")"
SESSION=""; unset SESSION
echo "» daemon response: $RESP" >&2
if [ "$RESP" != "OK" ]; then
  echo "✗ Daemon did not accept session : $RESP" >&2
  exit 1
fi

# `STATUS <slug>` : l'état de CETTE instance, au format historique (le `STATUS`
# nu rend désormais le tableau de bord de toutes les instances).
STATUS="$(printf 'STATUS %s\n' "$INSTANCE" | nc -N -U "$SOCK")"
echo "✓ Vault « $INSTANCE » unlocked. ${STATUS}"
