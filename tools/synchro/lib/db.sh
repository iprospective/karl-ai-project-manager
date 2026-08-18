#!/bin/bash
# db.sh — récupération du dump BDD depuis la prod + import local (générique,
# indépendant du type de site). Les adaptations spécifiques (config, domaine…)
# sont dans lib/<type>.sh::<type>_adapt_db.

DUMP_FILE=""   # rempli par db_dump_from_prod

# db_dump_from_prod → produit $DUMP_FILE (un .sql.gz dans $TMP_PATH).
# Stratégies (conf : DB_DUMP_STRATEGY) :
#   remote-backup-script (défaut) : la prod a un backup/mysqlbackup_all.sh qui
#       génère backup/mysql/<db>.sql.gz ; on l'exécute via ssh puis on rsync.
#   remote-mysqldump : on lance mysqldump à distance via ssh (creds prod requis :
#       REMOTE_DB_USER + REMOTE_DB_SECRET : URI de secret).
db_dump_from_prod() {
  mkdir -p "$TMP_PATH"
  DUMP_FILE="$TMP_PATH/$DB_TO.sql.gz"
  local strategy="${DB_DUMP_STRATEGY:-remote-backup-script}"
  log "Dump prod ($DB_FROM via $SSH_AUTH, stratégie=$strategy)"

  case "$strategy" in
    remote-backup-script)
      ssh $SSH_OPTS "$SSH_AUTH" -- backup/mysqlbackup_all.sh \
        || die "Échec du backup distant (backup/mysqlbackup_all.sh)."
      rsync -avz $RSYNC_OPTS "$SSH_AUTH:backup/mysql/$DB_FROM.sql.gz" "$DUMP_FILE" \
        || die "Échec rsync du dump distant."
      ;;
    remote-mysqldump)
      local rpass ruser="${REMOTE_DB_USER:?REMOTE_DB_USER requis pour remote-mysqldump}"
      rpass="$(resolve_secret "${REMOTE_DB_SECRET:?REMOTE_DB_SECRET requis}" password)" \
        || die "Impossible de résoudre le mot de passe BDD prod ($REMOTE_DB_SECRET)."
      # mdp passé via MYSQL_PWD côté distant (pas dans argv) ; --single-transaction
      ssh $SSH_OPTS "$SSH_AUTH" -- \
        "MYSQL_PWD=$(printf %q "$rpass") mysqldump --single-transaction --skip-comments -u$ruser $DB_FROM | gzip" \
        > "$DUMP_FILE" || die "Échec mysqldump distant."
      unset rpass
      ;;
    *) die "DB_DUMP_STRATEGY inconnue : $strategy" ;;
  esac
  [ -s "$DUMP_FILE" ] || die "Dump vide : $DUMP_FILE"
  ok "Dump récupéré : $DUMP_FILE ($(du -h "$DUMP_FILE" | cut -f1))"
}

# db_import → drop/create $DB_TO puis import du dump.
db_import() {
  log "Import dans la base locale $DB_TO (@$MYSQL_HOST)"
  mysql_local -e "DROP DATABASE IF EXISTS \`$DB_TO\`; CREATE DATABASE \`$DB_TO\` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;" \
    || die "Échec drop/create $DB_TO."
  if [ "${MYSQL_SANDBOX_ERROR:-0}" = "1" ]; then
    # contournement ligne sandbox mysqldump récent : /*!999999\- enable... */
    zcat "$DUMP_FILE" | tail -n +2 | mysql_local_db || die "Échec import (sandbox)."
  else
    zcat "$DUMP_FILE" | mysql_local_db || die "Échec import."
  fi
  ok "Import terminé."
}

# db_cleanup_dump → supprime le dump temporaire (appelé en fin de run).
db_cleanup_dump() {
  [ -n "$DUMP_FILE" ] && [ -f "$DUMP_FILE" ] && rm -f "$DUMP_FILE" && log "Dump temporaire supprimé."
}
