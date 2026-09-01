#!/bin/bash
# presta-nonprod-sql.sh — émet sur STDOUT le SQL qui rend un PrestaShop NON-PROD
# muet et inoffensif vis-à-vis des services cloud PrestaShop (RM2932).
#
# Le script n'ouvre JAMAIS de connexion : il écrit du SQL, l'appelant décide où
# l'exécuter. C'est ce qui le rend utilisable dans les trois contextes :
#
#   local (framework synchro)   presta-nonprod-sql.sh --domain x.local | mysql <db>
#   env de session (clone)      pm-env-session l'injecte via le helper `db-post-sql`
#   env distant (recette)       presta-nonprod-sql.sh --domain x.test.iprospective.fr \
#                                 | ssh <hôte> "mysql <db>"
#
# CE QUE FAIT LE SQL
#   1. aligne le domaine (`shop_url`, PS_SHOP_DOMAIN/_SSL) si --domain est fourni ;
#   2. PURGE les identités cloud héritées de la production ;
#   3. désactive les modules qui dialoguent avec ces services.
#
# POURQUOI PURGER L'IDENTITÉ PLUTÔT QUE « CONFIRMER »
#   Le bandeau « Action requise : confirmez l'URL de votre boutique » vient de
#   ps_accounts (AdminAjaxPsAccountsController) : il compare l'URL enregistrée
#   CHEZ PRESTASHOP CLOUD à l'URL locale, et s'affiche dès qu'elles diffèrent —
#   ce qui est structurel sur un clone. Aligner shop_url ne suffit donc PAS.
#   ⚠ Et surtout : le bouton « confirmer » RÉASSOCIE l'identité cloud au domaine
#   courant. Cliqué depuis un env de test, il déplace l'identité de la PRODUCTION
#   sur le domaine de test — c'est la prod qu'on casse. On délie, on ne confirme
#   jamais.
#   La purge suffit à faire taire le bandeau : le contrôleur sort en `return []`
#   quand l'URL cloud est vide.
#
# ENJEU AU-DELÀ DU BANDEAU
#   Un clone porte aussi les identifiants MARCHAND de la prod : PS_CHECKOUT_PAYPAL_*
#   (compte PayPal), PS_PSX_FIREBASE_* et les tokens ps_accounts. Un env de test qui
#   les garde peut émettre vers les services de la production.
#
# APRÈS EXÉCUTION : purger `var/cache/` du site — PrestaShop met ps_configuration
# en cache et continuerait à servir les anciennes valeurs.
#
# Idempotent : rejouable sans effet de bord (DELETE/UPDATE seulement).
set -euo pipefail

PREFIX="ps_"
DOMAIN=""
FORCE=0
DISABLE=1
MODULES="ps_accounts ps_eventbus ps_metrics ps_checkout psaddonsconnect"

usage() {
  awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"
  cat <<'USAGE'

Options :
  --prefix <p>            préfixe des tables (défaut : ps_)
  --domain <host>         domaine servi par l'env ; aligne shop_url + PS_SHOP_DOMAIN(_SSL)
  --modules "<a b c>"     modules à désactiver (défaut : ps_accounts ps_eventbus
                          ps_metrics ps_checkout psaddonsconnect)
  --no-disable-modules    purge les identités sans désactiver aucun module
  --force                 accepte un --domain qui ne ressemble pas à un domaine non-prod
  -h, --help              cette aide
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="${2:?--prefix attend une valeur}"; shift 2 ;;
    --domain) DOMAIN="${2:?--domain attend une valeur}"; shift 2 ;;
    --modules) MODULES="${2:?--modules attend une valeur}"; shift 2 ;;
    --no-disable-modules) DISABLE=0; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "presta-nonprod-sql: option inconnue : $1" >&2; exit 2 ;;
  esac
done

case "$PREFIX" in
  *[!a-zA-Z0-9_]*) echo "presta-nonprod-sql: préfixe invalide : $PREFIX" >&2; exit 2 ;;
esac

# Garde : un domaine de PROD ici signerait une erreur de cible. Le script n'exécute
# rien, mais il refuse de fabriquer le SQL qui déliera une production.
if [ -n "$DOMAIN" ]; then
  case "$DOMAIN" in
    *[!a-zA-Z0-9.-]*) echo "presta-nonprod-sql: domaine invalide : $DOMAIN" >&2; exit 2 ;;
  esac
  case "$DOMAIN" in
    *.local|*.lxc|*.test|*.test.*|*-test.*|*.dev.*|*-dev.*|*.preprod.*|*-preprod.*|localhost) : ;;
    *)
      if [ "$FORCE" != "1" ]; then
        echo "presta-nonprod-sql: '$DOMAIN' n'a pas l'air d'un domaine de dev/test." >&2
        echo "  Ce SQL DÉLIE la boutique de son compte PrestaShop et purge ses identifiants" >&2
        echo "  marchands : joué sur une PRODUCTION, il casse la boutique." >&2
        echo "  Si la cible est bien un env non-prod sur un domaine atypique : --force." >&2
        exit 2
      fi
      echo "-- ⚠ --force : '$DOMAIN' ne ressemble pas à un domaine de dev/test."
      ;;
  esac
fi

p="$PREFIX"

echo "-- SQL de neutralisation NON-PROD (presta-nonprod-sql.sh, RM2932)"
echo "-- Généré le $(date -Iseconds)"

if [ -n "$DOMAIN" ]; then
  cat <<SQL

-- 1. Domaine servi par l'environnement
UPDATE \`${p}shop_url\` SET domain = '${DOMAIN}', domain_ssl = '${DOMAIN}' WHERE main = 1;
UPDATE \`${p}configuration\` SET value = '${DOMAIN}'
  WHERE name IN ('PS_SHOP_DOMAIN', 'PS_SHOP_DOMAIN_SSL');
SQL
else
  echo
  echo "-- 1. Domaine : non aligné (--domain absent)"
fi

cat <<SQL

-- 2. Identités cloud héritées de la production
--    ps_accounts : jetons Firebase/OAuth, clés RSA, preuve de boutique et statut
--    caché (PS_ACCOUNTS_SHOP_STATUS) d'où sort l'URL cloud comparée par le bandeau.
--    PSX/ps_checkout : identité Firebase + compte PayPal MARCHAND.
DELETE FROM \`${p}configuration\` WHERE name LIKE 'PS_ACCOUNTS%';
DELETE FROM \`${p}configuration\` WHERE name LIKE 'PS_PSX_%';
DELETE FROM \`${p}configuration\` WHERE name LIKE 'PS_CHECKOUT_PAYPAL_%';
DELETE FROM \`${p}configuration\` WHERE name LIKE 'PS_EVENTBUS%';
DELETE FROM \`${p}configuration\` WHERE name LIKE 'PS_METRICS%';
SQL

if [ "$DISABLE" = "1" ] && [ -n "${MODULES// /}" ]; then
  list=""
  for m in $MODULES; do
    case "$m" in
      *[!a-zA-Z0-9_-]*) echo "presta-nonprod-sql: nom de module invalide : $m" >&2; exit 2 ;;
    esac
    list="${list}${list:+, }'${m}'"
  done
  cat <<SQL

-- 3. Modules qui dialoguent avec les services cloud / marchand
UPDATE \`${p}module\` SET active = 0 WHERE name IN (${list});
SQL
else
  echo
  echo "-- 3. Modules : laissés en l'état (--no-disable-modules)"
fi
