#!/bin/bash
# sync.sh — synchronise un site PROD → environnement LOCAL de test (fichiers + BDD)
# et applique les adaptations locales (domaine/vhost, emails, maintenance…).
#
# Usage :
#   ./sync.sh <env>            # charge environments/<env>.conf
#   ./sync.sh /chemin/x.conf   # charge une conf explicite (ex: conf dans le projet)
#   ./sync.sh <env> --files    # fichiers seulement
#   ./sync.sh <env> --db       # BDD seulement
#   ./sync.sh <env> --data     # seulement les dossiers de données du manifeste (env sous git)
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
DO_FILES=1; DO_DB=1; DO_DATA=0
for opt in "$@"; do
  case "$opt" in
    --files) DO_DB=0 ;;
    --db)    DO_FILES=0 ;;
    # RM3419 : les seuls DOSSIERS DE DONNÉES du manifeste (`presta-data.map` + surcharge du
    # site), sans toucher au reste de l'arbre. C'est le mode d'un env sous git : l'étape
    # `--files` fait un `rsync --delete` de TOUT le site, ce qui écraserait les fichiers du
    # dépôt et remplacerait les liens de données partagées par des dossiers réels.
    --data)  DO_FILES=0; DO_DB=0; DO_DATA=1 ;;
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

# Un DOMAIN bâti sur ${TEST_DOMAIN} ou ${DEV_DOMAIN} alors que ces clés manquent se
# termine par un point (« monsite. ») : il passerait la validation ci-dessus et
# produirait un vhost et des URL invalides. Arrêt ici, avant tout accès à la prod.
case "$DOMAIN" in
  *.) die "DOMAIN='$DOMAIN' est incomplet : TEST_DOMAIN/DEV_DOMAIN n'est pas défini pour cette instance. Ajoute TEST_DOMAIN, TEST_HOST et DEV_DOMAIN au pm.env de l'instance (RM3221)." ;;
esac

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

# 1 bis) Données seules (RM3419) — déclarées au manifeste, jamais le reste de l'arbre
if [ "$DO_DATA" = "1" ]; then
  type "${WEBSITE_TYPE}_sync_data" >/dev/null 2>&1 \
    || die "--data n'est pas implémenté pour le type $WEBSITE_TYPE (lib/$WEBSITE_TYPE.sh)."
  "${WEBSITE_TYPE}_sync_data"
fi

# 2) BDD : dump prod → import local → adaptations
if [ "$DO_DB" = "1" ]; then
  mysql_local_init
  db_dump_from_prod
  db_import
  "${WEBSITE_TYPE}_adapt_db"
  run_post_adapt_hook
fi

echo
ok "Synchro $ARG terminée."
warn "Étape MANUELLE : git checkout de la branche de test dans $WORKSPACE_ROOT/$WEBSITE_PATH"
