#!/bin/bash
# sync.sh — synchronise un site PROD → environnement LOCAL de test (fichiers + BDD)
# et applique les adaptations locales (domaine/vhost, emails, maintenance…).
#
# Usage :
#   ./sync.sh <env>            # charge environments/<env>.conf
#   ./sync.sh /chemin/x.conf   # charge une conf explicite (ex: conf dans le projet)
#   ./sync.sh <env> --files    # fichiers seulement
#   ./sync.sh <env> --db       # BDD seulement
#   ./sync.sh <env> --yes      # non interactif (ASSUME_YES)
#
# Le git checkout de la branche de test reste MANUEL (cf. workflow voulu) :
# après sync, faire `git checkout <branche-test>` dans le dossier de l'env.
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SELF_DIR/lib/common.sh"
. "$SELF_DIR/lib/helpers.sh"
. "$SELF_DIR/lib/db.sh"

[ "$#" -ge 1 ] || die "Usage : ./sync.sh <env|chemin.conf> [--files|--db] [--yes]"

ARG="$1"; shift
DO_FILES=1; DO_DB=1
for opt in "$@"; do
  case "$opt" in
    --files) DO_DB=0 ;;
    --db)    DO_FILES=0 ;;
    --yes|-y) export ASSUME_YES=1 ;;
    *) die "Option inconnue : $opt" ;;
  esac
done

# Résolution de la conf : chemin explicite, sinon environments/<env>.conf
if [ -f "$ARG" ]; then
  CONF="$ARG"
else
  CONF="$SELF_DIR/environments/$ARG.conf"
fi
[ -f "$CONF" ] || die "Conf introuvable : $CONF"
log "Environnement : $ARG"
# shellcheck disable=SC1090
. "$CONF"

# Validation minimale
: "${WEBSITE_TYPE:?WEBSITE_TYPE manquant dans la conf}"
: "${WEBSITE_PATH:?}" "${SSH_AUTH:?}" "${DB_FROM:?}" "${DB_TO:?}" "${DOMAIN:?}"

# Charge le module de type
TYPE_LIB="$SELF_DIR/lib/$WEBSITE_TYPE.sh"
[ -f "$TYPE_LIB" ] || die "Type non supporté : $WEBSITE_TYPE (pas de lib/$WEBSITE_TYPE.sh)"
# shellcheck disable=SC1090
. "$TYPE_LIB"

guard_local_target

# Nettoyage garanti du fichier d'auth MySQL + dump temporaire
MYSQL_DEFAULTS_FILE=""
cleanup() {
  [ -n "${MYSQL_DEFAULTS_FILE:-}" ] && [ -f "$MYSQL_DEFAULTS_FILE" ] && rm -f "$MYSQL_DEFAULTS_FILE"
  db_cleanup_dump
}
trap cleanup EXIT

echo
log "=== Synchro $ARG ($WEBSITE_TYPE) : $DB_FROM@prod → $DB_TO@local ==="
log "Cible fichiers : $WORKSPACE_ROOT/$WEBSITE_PATH | domaine : $DOMAIN"
echo

# 1) Fichiers
if [ "$DO_FILES" = "1" ]; then
  "${WEBSITE_TYPE}_sync_files"
fi

# 2) BDD : dump prod → import local → adaptations
if [ "$DO_DB" = "1" ]; then
  mysql_local_init
  db_dump_from_prod
  db_import
  "${WEBSITE_TYPE}_adapt_db"
fi

echo
ok "Synchro $ARG terminée."
warn "Étape MANUELLE : git checkout de la branche de test dans $WORKSPACE_ROOT/$WEBSITE_PATH"
