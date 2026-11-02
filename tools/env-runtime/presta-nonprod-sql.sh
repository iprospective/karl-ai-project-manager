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
#   3. désactive les modules qui dialoguent avec ces services ;
#   4. désactive les modules de SUIVI publicitaire et d'audience (RM3619).
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
# POURQUOI LE SUIVI PUBLICITAIRE (RM3619)
#   Les pixels et balises (Meta, Google Ads, Analytics, Tag Manager) d'un clone
#   gardent les identifiants de la prod : chaque visite d'une copie — recette,
#   robots, vrais visiteurs d'un site de test indexé — compte dans les statistiques
#   publicitaires et d'audience du client. Incident fondateur : RM3616 (calicote,
#   2026-11-02), recette indexée par Google, pixels déclenchés à chaque page.
#   On désactive le module, on ne touche pas à sa configuration : le réactiver
#   pour une recette du suivi lui-même reste un geste simple et délibéré.
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
TRACKING=1
TRACKING_MODULES="facebookproductad gadwordstracking ps_googleanalytics cdc_googletagmanager ps_facebook psxmarketingwithgoogle"

usage() {
  awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"
  cat <<'USAGE'

Options :
  --prefix <p>            préfixe des tables (défaut : ps_)
  --domain <host>         domaine servi par l'env ; aligne shop_url + PS_SHOP_DOMAIN(_SSL)
  --modules "<a b c>"     modules à désactiver (défaut : ps_accounts ps_eventbus
                          ps_metrics ps_checkout psaddonsconnect)
  --tracking-modules "<a b>"  modules de suivi publicitaire/audience à désactiver (défaut :
                          facebookproductad gadwordstracking ps_googleanalytics
                          cdc_googletagmanager ps_facebook psxmarketingwithgoogle)
  --keep-tracking         laisse les modules de suivi en l'état (recette du suivi lui-même)
  --no-disable-modules    purge les identités sans désactiver aucun module (ni cloud, ni suivi)
  --force                 accepte un --domain qui ne ressemble pas à un domaine non-prod
  -h, --help              cette aide
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="${2:?--prefix attend une valeur}"; shift 2 ;;
    --domain) DOMAIN="${2:?--domain attend une valeur}"; shift 2 ;;
    --modules) MODULES="${2:?--modules attend une valeur}"; shift 2 ;;
    --tracking-modules) TRACKING_MODULES="${2?--tracking-modules attend une valeur}"; shift 2 ;;
    --keep-tracking) TRACKING=0; shift ;;
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

# Liste SQL quotée d'une liste de noms de modules ; refuse un nom qui n'en est pas un
# (il finit dans du SQL).
sql_list() {
  local out="" m
  for m in $1; do
    case "$m" in
      *[!a-zA-Z0-9_-]*) echo "presta-nonprod-sql: nom de module invalide : $m" >&2; return 2 ;;
    esac
    out="${out}${out:+, }'${m}'"
  done
  printf '%s' "$out"
}

# Valider AVANT d'émettre quoi que ce soit : une liste invalide ne doit pas produire
# un SQL à moitié écrit.
cloud_list=$(sql_list "$MODULES") || exit 2
tracking_list=$(sql_list "$TRACKING_MODULES") || exit 2

if [ "$DISABLE" = "1" ] && [ -n "$cloud_list" ]; then
  cat <<SQL

-- 3. Modules qui dialoguent avec les services cloud / marchand
UPDATE \`${p}module\` SET active = 0 WHERE name IN (${cloud_list});
SQL
else
  echo
  echo "-- 3. Modules : laissés en l'état (--no-disable-modules)"
fi

if [ "$DISABLE" = "1" ] && [ "$TRACKING" = "1" ] && [ -n "$tracking_list" ]; then
  cat <<SQL

-- 4. Modules de suivi publicitaire et d'audience (pixels de la prod) — RM3619
UPDATE \`${p}module\` SET active = 0 WHERE name IN (${tracking_list});
SQL
else
  echo
  echo "-- 4. Modules de suivi : laissés en l'état (--keep-tracking ou --no-disable-modules)"
fi
