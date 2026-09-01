#!/bin/bash
# presta.sh — synchro spécifique PrestaShop.
# Variables de conf attendues : WEBSITE_PATH, REMOTE_FILES_PATH, SSH_AUTH,
# THEME_NAME, DOMAIN, EMAIL, SYNC_URL, DB_PREFIX, et celles de common.sh.

# presta_sync_files → rsync prod → local + remises en état locales.
presta_sync_files() {
  local dest="$WORKSPACE_ROOT/$WEBSITE_PATH"
  [ -d "$dest" ] || die "Cible inexistante : $dest (crée le dossier de l'env de test d'abord)."
  cd "$dest" || die "cd $dest impossible."

  log "rsync fichiers prod → $dest"
  confirm "rsync --delete depuis $SSH_AUTH:$REMOTE_FILES_PATH/ vers $dest/ — continuer ?"
  rsync -avz --delete $RSYNC_OPTS \
    --exclude="/.git" \
    --exclude="admin*/autoupgrade/backup" \
    --exclude="app/config/parameters.php" \
    --exclude="/img/tmp" \
    --exclude="/var/cache/" \
    --exclude="/var/logs/" \
    --exclude="/themes/$THEME_NAME/assets/cache" \
    "$SSH_AUTH:$REMOTE_FILES_PATH/" "$dest/" \
    || die "Échec rsync fichiers."

  log "Permissions des dossiers inscriptibles par PHP"
  chmod 775 img/tmp var/cache var/logs "themes/$THEME_NAME/assets/cache" 2>/dev/null
  find . -type d -name "*yaml" -exec chmod 0775 {} \; 2>/dev/null

  log "Purge des caches"
  sudo -u "$PHP_USER" rm -rf "$dest/var/cache/"* 2>/dev/null
  sudo -u "$PHP_USER" rm -rf "$dest/themes/$THEME_NAME/assets/cache/"* 2>/dev/null

  log "robots.txt → Disallow / (env non public)"
  printf 'User-agent: *\nDisallow: /\n' > "$dest/robots.txt"

  log "Suppression .user.ini"
  rm -f "$dest/.user.ini"

  if [ ! -e "$dest/fr/index.php" ]; then
    log "Création symlink /fr/index.php"
    mkdir -p "$dest/fr" && ln -sf ../index.php "$dest/fr/index.php"
  fi

  warn "@todo manuel : adapter app/config/parameters.php (BDD locale) et .htaccess (retirer le domaine prod)."
  ok "Fichiers synchronisés."
}

# presta_adapt_db → adaptations de ps_configuration / ps_shop_url pour le local.
presta_adapt_db() {
  log "Adaptation de la configuration PrestaShop ($DB_TO)"
  local p="$DB_PREFIX"
  mysql_local_db <<SQL || die "Échec adaptation config PrestaShop."
-- Boutique désactivée (maintenance) + SSL off en local
UPDATE ${p}configuration SET value = NULL WHERE name='PS_SHOP_ENABLE';
UPDATE ${p}configuration SET value = 0 WHERE name IN ('PS_SSL_ENABLED','PS_SSL_ENABLED_EVERYWHERE');
-- Toutes les notifications mail redirigées vers l'adresse de dev
UPDATE ${p}configuration SET value = '${EMAIL}'
  WHERE name IN ('PS_SHOP_EMAIL','DLCDLUO_EMAILS','MMI_PRODUCT_NOTIFICATION_EMAIL',
                 'MMI_ORDER_EMAIL_ALERT_CORSE','PS_MAIL_USER','MA_MERCHANT_MAILS',
                 'DPDFRANCE_EMAIL_EXP','WELCO_EMAIL_EXP','Sendin_smtpSender','PS_LOGS_EMAIL_RECEIVERS');
-- CORS + domaine
UPDATE ${p}configuration SET value = '["https:\/\/${DOMAIN}"]' WHERE name='SC_CORS_DOMAINS';
UPDATE ${p}configuration SET value = '${DOMAIN}' WHERE name IN ('PS_SHOP_DOMAIN','PS_SHOP_DOMAIN_SSL');
UPDATE ${p}shop_url SET domain='${DOMAIN}', domain_ssl='${DOMAIN}' WHERE id_shop=1;
-- Whitelist IP en maintenance pour pouvoir naviguer
UPDATE ${p}configuration SET value = CONCAT(COALESCE(value,''), ',${CLIENT_USER_IP}')
  WHERE name='PS_MAINTENANCE_IP' AND COALESCE(value,'') NOT LIKE '%${CLIENT_USER_IP}%';
SQL

  # Neutralisation des services cloud PrestaShop (RM2932). Un clone de prod hérite
  # de l'identité PrestaShop Account de la boutique et de ses identifiants marchands :
  # il affiche « Action requise : confirmez l'URL de votre boutique » (bandeau
  # ps_accounts, insoluble par un simple alignement de domaine) et peut émettre vers
  # les services de la production. Le SQL est produit par un script partagé, pour que
  # le même geste s'applique aux envs de session et aux envs de recette distants.
  local nonprod="$SELF_DIR/../env-runtime/presta-nonprod-sql.sh"
  if [ -x "$nonprod" ]; then
    "$nonprod" --prefix "$p" --domain "$DOMAIN" | mysql_local_db \
      || die "Échec neutralisation des services cloud PrestaShop."
    ok "Services cloud PrestaShop neutralisés (identités purgées, modules désactivés)."
  else
    warn "presta-nonprod-sql.sh introuvable ($nonprod) — bandeau ps_accounts et jetons marchands NON neutralisés."
  fi

  # URL de sync DoliPrestaSync : positionnée si fournie, sinon supprimée
  if [ -n "${SYNC_URL:-}" ]; then
    mysql_local_db -e "UPDATE ${p}configuration SET value='${SYNC_URL}' WHERE name='MMI_SYNC_WS_SYNC_URL';"
  else
    mysql_local_db -e "DELETE FROM ${p}configuration WHERE name='MMI_SYNC_WS_SYNC_URL';"
  fi
  ok "Configuration PrestaShop adaptée pour $DOMAIN."
}
