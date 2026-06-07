#!/bin/bash
# dolibarr.sh — synchro spécifique Dolibarr (ERP/CRM).
#
# Particularité Dolibarr vs PrestaShop : l'URL/domaine, le chemin des documents
# et la connexion BDD vivent dans htdocs/conf/conf.php (FICHIER, hors BDD). Donc
# après import de la base de prod il n'y a RIEN à réécrire côté URL — le conf.php
# local pointe déjà vers la base et le domaine locaux. La seule adaptation BDD
# nécessaire est de neutraliser l'envoi de mails réels (la table llx_const porte
# la config SMTP de prod).
#
# On NE synchronise JAMAIS htdocs/ (c'est le code, versionné/édité en dev) :
# dolibarr_sync_files ne rapatrie que le dossier documents/ (pièces jointes,
# PDF générés, ECM…). Pour un simple rafraîchissement de la base, lancer
# `./sync.sh <env> --db` et sauter complètement cette étape.
#
# Variables de conf attendues : WEBSITE_PATH (racine projet contenant htdocs/ et
# documents/), REMOTE_FILES_PATH (chemin documents/ côté prod), SSH_AUTH, DOMAIN,
# EMAIL, DB_PREFIX, + celles de common.sh.

# dolibarr_sync_files → rsync du SEUL dossier documents/ prod → local.
dolibarr_sync_files() {
  local dest="$WORKSPACE_ROOT/$WEBSITE_PATH/documents"
  [ -d "$dest" ] || die "Cible inexistante : $dest (dossier documents/ de l'env de dev)."

  log "rsync documents/ prod → $dest (le code htdocs/ n'est PAS touché)"
  confirm "rsync --delete depuis $SSH_AUTH:$REMOTE_FILES_PATH/ vers $dest/ — continuer ?"
  rsync -avz --delete $RSYNC_OPTS \
    --exclude="/admin/temp/" \
    --exclude="/admin/temp.*/" \
    "$SSH_AUTH:$REMOTE_FILES_PATH/" "$dest/" \
    || die "Échec rsync documents."

  log "Permissions documents/ inscriptibles par PHP ($PHP_USER)"
  chmod -R u+rwX "$dest" 2>/dev/null
  ok "Documents synchronisés."
}

# dolibarr_adapt_db → neutralise tout ce qui pourrait, depuis le dev, atteindre
# le monde réel ou la prod (mails clients, encaissements, sync PrestaShop, IMAP).
# Tout passe par la table de config llx_const (clé unique (name, entity)).
#
# Variables de conf optionnelles (sinon valeurs par défaut locales) :
#   DOLI_SYNC_PS_URL  : URL de la boutique PrestaShop locale (def: http://<DOMAIN presta>)
#   DOLI_SYNC_WS_URL  : URL du webservice de sync local
dolibarr_adapt_db() {
  local p="$DB_PREFIX"
  local ps_url="${DOLI_SYNC_PS_URL:-}"
  local ws_url="${DOLI_SYNC_WS_URL:-}"

  log "Adaptation Dolibarr ($DB_TO) : mails, paiements, sync, IMAP"
  mysql_local_db <<SQL || die "Échec adaptation config Dolibarr."
-- 1) MAILS : tout destinataire forcé vers l'adresse de dev, envoi en mode local
--    (php mail), creds SMTP externes (Brevo/Sendinblue…) vidés par sécurité.
INSERT INTO ${p}const (name, entity, value, type, visible, note)
VALUES ('MAIN_MAIL_FORCE_SENDTO', 1, '${EMAIL}', 'chaine', 0, 'Forcé par synchro dev')
ON DUPLICATE KEY UPDATE value='${EMAIL}', note='Forcé par synchro dev';
UPDATE ${p}const SET value='mail' WHERE name='MAIN_MAIL_SENDMODE';
UPDATE ${p}const SET value=''
  WHERE name IN ('MAIN_MAIL_SMTP_SERVER','MAIN_MAIL_SMTPS_ID','MAIN_MAIL_SMTPS_PW',
                 'MAIN_MAIL_SMTPS_PW_OAUTH_SERVICE','MAIN_MAIL_SMTPS_AUTH_TYPE');
-- Module multi-SMTP + collecteur IMAP (pointait sur la boîte de prod) : OFF.
UPDATE ${p}const SET value='0' WHERE name IN ('MULTISMTP_SMTP_ENABLED','MULTISMTP_IMAP_ENABLED');

-- 2) PAIEMENTS : tout PSP en mode test/sandbox (pas d'encaissement réel).
UPDATE ${p}const SET value='1' WHERE name='MBIETRANSACTIONS_TEST';   -- paiement par lien
UPDATE ${p}const SET value='1' WHERE name='PAYPAL_API_SANDBOX';

-- 3) SYNC Dolibarr ↔ PrestaShop : master switch OFF (ne JAMAIS pousser vers la
--    prod depuis le dev), et URLs repointées en local si fournies dans la conf.
UPDATE ${p}const SET value='0' WHERE name='MMIPRESTASYNC_SYNC';
SQL

  [ -n "$ps_url" ] && mysql_local_db -e \
    "UPDATE ${p}const SET value='${ps_url}' WHERE name='MMIPRESTASYNC_PS_URL';"
  [ -n "$ws_url" ] && mysql_local_db -e \
    "UPDATE ${p}const SET value='${ws_url}' WHERE name='MMIPRESTASYNC_WS_SYNC_URL';"

  ok "Config Dolibarr adaptée : mails→$EMAIL, paiements en test, sync OFF."
  warn "Rappels (non automatisés) :"
  warn "  • Pour faire tourner la sync EN LOCAL : remettre MMIPRESTASYNC_SYNC=1 et"
  warn "    MMIPRESTASYNC_WS_SYNC_PASS = WS_PASSWORD du dpsync local (config.inc.php)."
  warn "  • user 'synchro' garde son api_key (= clé API dev, OK)."
  warn "  • cron Dolibarr : inactif sauf si un cron système appelle public/cron/."
}
