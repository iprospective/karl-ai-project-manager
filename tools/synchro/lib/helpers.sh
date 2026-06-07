#!/bin/bash
# helpers.sh — fonctions utilitaires partagées (log, confirmation, garde-fous,
# résolution de secret Vaultwarden, auth MySQL sécurisée).

# --- logging ---------------------------------------------------------------
log()  { printf '\033[1;34m▶\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# --- confirmation interactive ---------------------------------------------
# confirm "message"  → exit 1 si l'utilisateur ne tape pas "oui".
# Outrepassable avec ASSUME_YES=1 (non interactif).
confirm() {
  [ "${ASSUME_YES:-0}" = "1" ] && return 0
  local reply
  read -r -p "$1 [oui/non] " reply
  [ "$reply" = "oui" ] || die "Annulé par l'utilisateur."
}

# --- garde-fou : ne JAMAIS écrire vers une cible qui ressemble à de la prod -
# La synchro va vers un environnement LOCAL de test/dev. On refuse si le nom
# de base ou le domaine cible n'a pas l'air local.
guard_local_target() {
  case "$DB_TO" in
    # Suffixes "locaux" reconnus. *_dolibarr couvre les bases Dolibarr de dev
    # (ex: calicote_dolibarr) dont le nom n'a pas de suffixe _dev ; aucune base
    # de PROD ici n'est nommée *_dolibarr (prod = erp_calicote, sono0634_doli966…).
    *_test|*_dev|*_presta|*_sync|*_preprod|*_local|*_dolibarr) : ;;
    *) die "DB_TO='$DB_TO' ne ressemble pas à une base locale (suffixe _test/_dev/...). Sécurité : abandon." ;;
  esac
  case "$DOMAIN" in
    *.local|*.test.*|*.dev.*) : ;;
    *) warn "DOMAIN='$DOMAIN' n'a pas l'air d'un domaine local/test — vérifie la conf." ;;
  esac
}

# --- Vaultwarden -----------------------------------------------------------
# resolve_secret "vaultwarden://org/col/item" [field] → valeur sur stdout.
# IMPORTANT : ne fait PAS exit (utilisé en substitution de commande). Renvoie
# un code != 0 en cas d'échec ; le message part sur stderr. Le caller DOIT
# tester le code (ex: val="$(resolve_secret …)" || die …).
RESOLVE_SECRET_BIN="/zfs/workspaces/ai/project-management/scripts/resolve-secret.sh"
resolve_secret() {
  local uri="$1" field="${2:-password}"
  if [ ! -x "$RESOLVE_SECRET_BIN" ]; then
    echo "resolve-secret.sh introuvable ($RESOLVE_SECRET_BIN)." >&2; return 4
  fi
  local val rc
  val="$("$RESOLVE_SECRET_BIN" "$uri" "$field")"; rc=$?
  case $rc in
    0) printf '%s' "$val"; return 0 ;;
    2) echo "Coffre Vaultwarden verrouillé → ! /zfs/workspaces/ai/project-management/scripts/unlock-vault.sh" >&2 ;;
    3) echo "vault-agentd non lancé → ! /zfs/workspaces/ai/project-management/scripts/unlock-vault.sh" >&2 ;;
    *) echo "Échec résolution secret '$uri' (code $rc)." >&2 ;;
  esac
  return "$rc"
}

# --- MySQL : auth locale (jamais de mot de passe en argv) -------------------
# Deux modes selon $MYSQL_ADMIN_SECRET :
#   - vide (dev local) → on s'appuie sur le ~/.my.cnf de l'utilisateur (root) ;
#     on ajoute juste -h $MYSQL_HOST.
#   - vaultwarden://… → on construit un --defaults-file dédié (0600, ignore
#     ~/.my.cnf) avec user=$MYSQL_ADMIN_USER + mot de passe résolu (abort si échec).
# Le fichier temporaire est supprimé par le trap de sync.sh.
MYSQL_AUTH_ARGS=()
mysql_local_init() {
  case "${MYSQL_ADMIN_SECRET:-}" in
    vaultwarden://*)
      local pass
      pass="$(resolve_secret "$MYSQL_ADMIN_SECRET" password)" \
        || die "Impossible de résoudre le mot de passe admin MySQL ($MYSQL_ADMIN_SECRET)."
      [ -n "$pass" ] || die "Mot de passe admin MySQL vide après résolution Vaultwarden."
      MYSQL_DEFAULTS_FILE="$(mktemp "${TMPDIR:-/tmp}/.synchro-my.XXXXXX")"
      chmod 600 "$MYSQL_DEFAULTS_FILE"
      printf '[client]\nhost=%s\nuser=%s\npassword=%s\n' \
        "$MYSQL_HOST" "$MYSQL_ADMIN_USER" "$pass" > "$MYSQL_DEFAULTS_FILE"
      unset pass
      MYSQL_AUTH_ARGS=(--defaults-file="$MYSQL_DEFAULTS_FILE")
      ;;
    "")
      log "Auth MySQL locale via ~/.my.cnf (host $MYSQL_HOST)."
      MYSQL_AUTH_ARGS=(-h "$MYSQL_HOST")
      ;;
    *) die "MYSQL_ADMIN_SECRET doit être une URI vaultwarden:// ou vide (reçu: $MYSQL_ADMIN_SECRET)." ;;
  esac
  mysql "${MYSQL_AUTH_ARGS[@]}" -e "SELECT 1;" >/dev/null 2>&1 \
    || die "Connexion MySQL locale impossible (host=$MYSQL_HOST). Vérifie ~/.my.cnf ou MYSQL_ADMIN_SECRET."
}
mysql_local()    { mysql "${MYSQL_AUTH_ARGS[@]}" "$@"; }
mysql_local_db() { mysql "${MYSQL_AUTH_ARGS[@]}" "$DB_TO" "$@"; }
