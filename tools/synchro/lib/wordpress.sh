#!/bin/bash
# wordpress.sh — synchro spécifique WordPress (RM3250) : clone prod → recette.
#
# Variables de conf attendues (en plus de celles de common.sh / sync.sh) :
#   REMOTE_FILES_PATH   racine WordPress sur la prod (lue par rsync via SSH_AUTH)
#   PROD_URL            URL publique de la prod (https://www.exemple.fr) — remplacée
#                       par https://$DOMAIN dans toute la base
#   EMAIL               adresse qui reçoit admin_email sur la recette
# Optionnelles :
#   DB_PREFIX           préfixe des tables (défaut wp_)
#   WP_CLI              commande wp-cli sur la cible, avec l'utilisateur et le PHP du
#                       site (défaut « wp ») — ex. "sudo -u php_x php8.4 /usr/local/bin/wp"
#   FILES_OWNER         user:group appliqué aux fichiers copiés (rsync --chown)
#   DB_USER_LOCAL       compte MySQL du site sur la cible (défaut : $DB_TO)
#   WP_DEACTIVATE_PLUGINS  extensions désactivées sur la recette : celles qui parlent à
#                       un service de la prod (pare-feu, cache, sauvegarde distante…)
#   WP_RECETTE_MU       fichiers PHP propres au site, posés en mu-plugins de recette
#                       (ex. retirer un traceur d'audience) ; chemins lisibles sur la cible
#
# Ce que la recette ne doit JAMAIS faire, et comment c'est garanti :
#   - envoyer un mail réel      → mu-plugin zz-pm-recette.php (pre_wp_mail)
#   - être indexée              → blog_public=0 + en-tête X-Robots-Tag + robots.txt fermé
#   - pointer vers la prod      → search-replace de l'URL ET du chemin disque (wp-cli :
#                                 sûr pour les données sérialisées, contrairement à un sed)
# Les mu-plugins de recette survivent à un `--files` seul : rsync les exclut, donc ne
# les supprime pas malgré --delete.

WP_RECETTE_MU_PREFIX="zz-pm-recette"

_wp_dest() { printf '%s' "$WORKSPACE_ROOT/$WEBSITE_PATH"; }

# wp_cli <args…> → exécute wp-cli sur la recette.
wp_cli() {
  # shellcheck disable=SC2086 # WP_CLI est une ligne de commande, découpage voulu
  ${WP_CLI:-wp} --path="$(_wp_dest)" "$@"
}

# _wp_host <url> → hôte d'une URL (sans schéma, port ni chemin).
_wp_host() {
  local h="${1#*://}"
  h="${h%%/*}"
  printf '%s' "${h%%:*}"
}

# wordpress_guard → refuse une conf qui écrirait sur la prod elle-même.
wordpress_guard() {
  : "${PROD_URL:?PROD_URL manquant dans la conf (URL publique de la prod)}"
  : "${REMOTE_FILES_PATH:?REMOTE_FILES_PATH manquant dans la conf}"
  local prod_host
  prod_host="$(_wp_host "$PROD_URL")"
  [ -n "$prod_host" ] || die "PROD_URL='$PROD_URL' illisible."
  [ "$prod_host" != "$DOMAIN" ] \
    || die "DOMAIN='$DOMAIN' est le domaine de la prod : la recette l'écraserait. Abandon."
}

# wordpress_sync_files → rsync prod → recette, puis ce qui rend la copie inoffensive.
wordpress_sync_files() {
  wordpress_guard
  local dest; dest="$(_wp_dest)"
  [ -d "$dest" ] || die "Cible inexistante : $dest (crée le dossier de la recette d'abord)."

  log "rsync fichiers prod → $dest"
  confirm "rsync --delete depuis $SSH_AUTH:$REMOTE_FILES_PATH/ vers $dest/ — continuer ?"
  local chown=()
  [ -n "${FILES_OWNER:-}" ] && chown=(--chown="$FILES_OWNER")
  # shellcheck disable=SC2086
  rsync -az --delete "${chown[@]}" $RSYNC_OPTS \
    --exclude="/.git" \
    --exclude="/wp-config.php" \
    --exclude="/.user.ini" \
    --exclude="/.maintenance" \
    --exclude="/wp-content/cache/" \
    --exclude="/wp-content/upgrade/" \
    --exclude="/wp-content/upgrade-temp-backup/" \
    --exclude="/wp-content/debug.log" \
    --exclude="/wp-content/mu-plugins/$WP_RECETTE_MU_PREFIX*.php" \
    "$SSH_AUTH:$REMOTE_FILES_PATH/" "$dest/" \
    || die "Échec rsync fichiers."

  log "robots.txt → Disallow / (recette non publique)"
  printf 'User-agent: *\nDisallow: /\n' > "$dest/robots.txt"

  wordpress_install_mu_plugins "$dest"
  [ -f "$dest/wp-config.php" ] || wordpress_make_config "$dest"
  ok "Fichiers synchronisés."
}

# wordpress_install_mu_plugins <dest> → mu-plugin générique de recette + ceux du site.
wordpress_install_mu_plugins() {
  local mu="$1/wp-content/mu-plugins" f
  mkdir -p "$mu" || die "mkdir $mu impossible."
  cat > "$mu/$WP_RECETTE_MU_PREFIX.php" <<'PHP'
<?php
/**
 * Recette — posé par tools/synchro (lib/wordpress.sh, RM3250). Ne pas copier en prod.
 *
 * Un clone de la prod garde ses formulaires, ses comptes et ses tâches planifiées :
 * sans ce fichier, il enverrait de vrais mails à de vrais destinataires.
 */
add_filter( 'pre_wp_mail', static function ( $retour, $atts ) {
	$to = is_array( $atts['to'] ?? null ) ? implode( ', ', $atts['to'] ) : (string) ( $atts['to'] ?? '' );
	error_log( '[recette] mail non envoyé → ' . $to . ' : ' . ( $atts['subject'] ?? '' ) );
	return true;
}, 10, 2 );

add_action( 'send_headers', static function () {
	header( 'X-Robots-Tag: noindex, nofollow', true );
} );
PHP
  for f in ${WP_RECETTE_MU:-}; do
    [ -f "$f" ] || die "WP_RECETTE_MU : fichier introuvable : $f"
    cp "$f" "$mu/$WP_RECETTE_MU_PREFIX-$(basename "$f")" || die "Copie de $f impossible."
  done
  if [ -n "${FILES_OWNER:-}" ]; then
    chown "$FILES_OWNER" "$mu/$WP_RECETTE_MU_PREFIX"*.php || die "chown des mu-plugins impossible."
  fi
  ok "mu-plugins de recette posés (mails coupés, noindex)."
}

# wordpress_make_config <dest> → wp-config.php de la recette, avec son propre compte MySQL.
# Le mot de passe est tiré ici, passé à MySQL et à wp-cli par STDIN (jamais en argument,
# jamais affiché) : il n'existe que dans wp-config.php. Une synchro suivante garde le
# fichier (exclu du rsync) et ne tire donc pas de nouveau mot de passe.
wordpress_make_config() {
  local dest="$1" user="${DB_USER_LOCAL:-$DB_TO}" pass
  log "wp-config.php absent → création (base $DB_TO, compte $user)"
  # Une seule initialisation : chacune crée un fichier d'auth que seul le dernier
  # trap de sync.sh supprimerait.
  [ "${#MYSQL_AUTH_ARGS[@]}" -gt 0 ] || mysql_local_init
  pass="$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)"
  [ "${#pass}" -ge 24 ] || die "Tirage du mot de passe MySQL impossible."
  mysql_local <<SQL || die "Création du compte MySQL $user impossible."
CREATE USER IF NOT EXISTS '$user'@'localhost' IDENTIFIED BY '$pass';
ALTER USER '$user'@'localhost' IDENTIFIED BY '$pass';
GRANT ALL PRIVILEGES ON \`$DB_TO\`.* TO '$user'@'localhost';
SQL
  printf '%s\n' "$pass" | wp_cli config create --dbname="$DB_TO" --dbuser="$user" \
      --dbhost=localhost --dbprefix="${DB_PREFIX:-wp_}" --prompt=dbpass --skip-check \
      >/dev/null || die "wp config create a échoué."
  unset pass
  chmod 640 "$dest/wp-config.php"
  if [ -n "${FILES_OWNER:-}" ]; then
    chown "$FILES_OWNER" "$dest/wp-config.php" || die "chown de wp-config.php impossible."
  fi
  ok "wp-config.php créé."
}

# wordpress_adapt_db → la base importée cesse de se prendre pour la prod.
wordpress_adapt_db() {
  wordpress_guard
  local dest; dest="$(_wp_dest)"
  [ -f "$dest/wp-config.php" ] || die "wp-config.php absent : lance d'abord la synchro des fichiers."
  local prod_host url="https://$DOMAIN"
  prod_host="$(_wp_host "$PROD_URL")"

  log "search-replace $PROD_URL → $url (données sérialisées comprises)"
  # Formes rencontrées dans une base WordPress : URL complète, URL sans schéma, et la
  # même échappée en JSON (blocs Gutenberg, réglages d'extensions).
  wordpress_replace "$PROD_URL" "$url"
  wordpress_replace "//$prod_host" "//$DOMAIN"
  wordpress_replace "\\/\\/$prod_host" "\\/\\/$DOMAIN"
  if [ "$REMOTE_FILES_PATH" != "$dest" ]; then
    wordpress_replace "$REMOTE_FILES_PATH" "$dest"
  fi

  log "Recette non indexable, notifications vers $EMAIL"
  wp_cli option update blog_public 0 >/dev/null || die "blog_public non mis à jour."
  wp_cli option update admin_email "$EMAIL" >/dev/null || die "admin_email non mis à jour."
  wp_cli option delete new_admin_email >/dev/null 2>&1 || true

  # --skip-plugins : la routine de désactivation d'une extension appartient au site
  # qu'elle protège. Celle de CrowdSec appelle une fonction de son interface
  # d'administration, absente en ligne de commande : l'extension restait active sur la
  # recette, donc à interroger l'API locale d'une production qui n'est pas là.
  local p
  for p in ${WP_DEACTIVATE_PLUGINS:-}; do
    if wp_cli plugin is-active "$p" --skip-plugins --skip-themes >/dev/null 2>&1; then
      if wp_cli plugin deactivate "$p" --skip-plugins --skip-themes >/dev/null; then
        ok "Extension désactivée sur la recette : $p"
      else
        warn "Extension $p non désactivée."
      fi
    fi
  done

  rm -rf "${dest:?}/wp-content/cache/"* 2>/dev/null
  wp_cli cache flush >/dev/null 2>&1 || true
  ok "WordPress adapté pour $DOMAIN."
}

# wordpress_replace <de> <vers> → search-replace sur toutes les tables du préfixe.
wordpress_replace() {
  wp_cli search-replace "$1" "$2" --all-tables-with-prefix --skip-columns=guid \
      --report-changed-only --format=count >/dev/null \
    || die "search-replace '$1' → '$2' a échoué."
}
