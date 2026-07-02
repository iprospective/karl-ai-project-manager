#!/bin/bash
# pm-env-helper — helper PRIVILÉGIÉ pour le runtime des envs de workspace
# (RM1947 brique F1, consommé par scripts/pm-env-session.py — RM1834).
#
# Déployé sur la box de dev (dev.lxc) : /usr/local/sbin/pm-env-helper, root:root 755.
# Invoqué par l'user de dev via sudo NOPASSWD (sudoers.d/pm-env-helper) → TOUTE la
# sécurité repose ici : fail-closed, whitelist de verbes, validation stricte des
# arguments, aucun argument ne touche un shell sans validation.
#
# Verbes :
#   vhost-add <name> <docroot> <sock>   crée+active le vhost Apache <name>.lxc
#   vhost-remove <name>                 désactive+supprime (si géré par nous) + purge logs apache
#   db-clone <src> <dst>                CREATE DATABASE dst + copie (dst = *_rm<id> uniquement)
#   db-drop <db>                        DROP DATABASE (db = *_rm<id> uniquement)
#   phplog-purge <basename>             purge /var/log/php/<basename>.{error,slow}.log (basename *-rm<id>)
#
# Garde-fous :
#   - vhost <name> : ^[a-z0-9_.-]+-(rm[0-9]+|dev|test)$ ; remove exige le marqueur
#     « managed-by: pm-env-helper » dans le .conf (jamais de vhost tiers).
#   - docroot : sous /home/workspaces/ (realpath), doit exister.
#   - sock : /run/php/<pool>.sock existant.
#   - BDD : clone/drop UNIQUEMENT des noms suffixés _rm<id> (une BDD partagée
#     n'est jamais droppable) ; clone refuse d'écraser une dst existante.
#   - configtest Apache avant reload, rollback si KO.
#   - audit : chaque mutation est loguée dans syslog (logger -t pm-env-helper).

set -euo pipefail

MARKER="# managed-by: pm-env-helper"
WS_ROOT="/zfs/workspaces"
SITES="/etc/apache2/sites-available"

die() { echo "pm-env-helper: $*" >&2; exit 1; }
audit() { logger -t pm-env-helper -- "$SUDO_USER: $*" || true; }

[ "$(id -u)" = 0 ] || die "doit tourner en root (via sudo)"

vname_ok()  { [[ "$1" =~ ^[a-z0-9_.-]+-(rm[0-9]+|dev|test)$ ]]; }
dbname_ok() { [[ "$1" =~ ^[a-z0-9_]+$ ]]; }
db_ephemeral() { [[ "$1" =~ _rm[0-9]+$ ]]; }
db_exists() { mysql -NBe "SHOW DATABASES LIKE '$1'" | grep -qx "$1"; }

apache_apply() {
    # configtest puis reload ; en cas d'échec, exécute le rollback passé en argument.
    if ! apache2ctl configtest >/dev/null 2>&1; then
        eval "$1"
        die "apache configtest KO — modification annulée"
    fi
    systemctl reload apache2
}

cmd_vhost_add() {
    local name="$1" docroot="$2" sock="$3" conf real
    vname_ok "$name" || die "nom de vhost invalide : $name"
    real=$(realpath -e "$docroot" 2>/dev/null) || die "docroot introuvable : $docroot"
    [[ "$real" == "$WS_ROOT"/* ]] || die "docroot hors de $WS_ROOT : $real"
    [[ "$sock" =~ ^/run/php/[A-Za-z0-9_-]+\.sock$ ]] || die "sock invalide : $sock"
    [ -S "$sock" ] || die "sock inexistant : $sock"
    conf="$SITES/$name.conf"
    if [ -e "$conf" ]; then
        grep -qF "$MARKER" "$conf" || die "$name.conf existe et n'est pas géré par pm-env-helper"
    fi
    cat > "$conf" <<EOF
$MARKER
<VirtualHost *:80>
    ServerName $name.lxc

    DocumentRoot $real
    <Directory $real>
        Require all granted
        AllowOverride All
        DirectoryIndex index.php
        Options -Indexes +FollowSymLinks
    </Directory>

    <FilesMatch \.php\$>
        SetHandler "proxy:unix:$sock|fcgi://localhost/"
    </FilesMatch>

    # deny dotfiles (.user.ini, .env, .git…)
    <FilesMatch "^\.">
        Require all denied
    </FilesMatch>
    <DirectoryMatch "/\.">
        Require all denied
    </DirectoryMatch>

    ErrorLog  \${APACHE_LOG_DIR}/$name.error.log
    CustomLog \${APACHE_LOG_DIR}/$name.access.log combined
</VirtualHost>
EOF
    a2ensite -q "$name" >/dev/null
    apache_apply "a2dissite -q '$name' >/dev/null; rm -f '$conf'"
    audit "vhost-add $name docroot=$real sock=$sock"
    echo "✓ vhost $name.lxc → $real (pool $(basename "$sock" .sock))"
}

cmd_vhost_remove() {
    local name="$1" conf
    vname_ok "$name" || die "nom de vhost invalide : $name"
    conf="$SITES/$name.conf"
    [ -e "$conf" ] || { echo "· vhost $name absent — rien à faire"; return 0; }
    grep -qF "$MARKER" "$conf" || die "$name.conf n'est pas géré par pm-env-helper — refus"
    a2dissite -q "$name" >/dev/null 2>&1 || true
    rm -f "$conf"
    apache_apply ":"
    rm -f "/var/log/apache2/$name.error.log" "/var/log/apache2/$name.access.log"
    audit "vhost-remove $name"
    echo "✓ vhost $name supprimé (+ logs apache)"
}

cmd_db_clone() {
    local src="$1" dst="$2"
    dbname_ok "$src" || die "nom de BDD source invalide : $src"
    dbname_ok "$dst" || die "nom de BDD cible invalide : $dst"
    db_ephemeral "$dst" || die "cible non éphémère ($dst) : un clone doit être suffixé _rm<id>"
    db_exists "$src" || die "BDD source inexistante : $src"
    db_exists "$dst" && die "BDD cible existe déjà : $dst (db-drop d'abord si voulu)"
    mysql -e "CREATE DATABASE \`$dst\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    if ! mysqldump --single-transaction --routines --triggers "$src" | mysql "$dst"; then
        mysql -e "DROP DATABASE IF EXISTS \`$dst\`"
        die "copie $src → $dst échouée — clone annulé"
    fi
    # mêmes droits que la source pour les comptes applicatifs
    mysql -NBe "SELECT CONCAT('GRANT ALL PRIVILEGES ON \`$dst\`.* TO ''', User, '''@''', Host, ''';')
                FROM mysql.db WHERE Db = '$src' AND User <> ''" | mysql || true
    mysql -e "FLUSH PRIVILEGES"
    audit "db-clone $src → $dst"
    echo "✓ BDD $dst clonée depuis $src"
}

cmd_db_drop() {
    local db="$1"
    dbname_ok "$db" || die "nom de BDD invalide : $db"
    db_ephemeral "$db" || die "refus : $db n'est pas une BDD éphémère (_rm<id>)"
    db_exists "$db" || { echo "· BDD $db absente — rien à faire"; return 0; }
    mysql -e "DROP DATABASE \`$db\`"
    audit "db-drop $db"
    echo "✓ BDD $db supprimée"
}

cmd_phplog_purge() {
    local base="$1"
    [[ "$base" =~ ^[a-z0-9_.-]+-rm[0-9]+$ ]] || die "basename invalide (attendu <pool>-rm<id>) : $base"
    rm -f "/var/log/php/$base.error.log" "/var/log/php/$base.slow.log"
    audit "phplog-purge $base"
    echo "✓ logs php $base purgés"
}

verb="${1:-}"; shift || true
case "$verb" in
    vhost-add)    [ $# -eq 3 ] || die "usage: vhost-add <name> <docroot> <sock>"; cmd_vhost_add "$@";;
    vhost-remove) [ $# -eq 1 ] || die "usage: vhost-remove <name>"; cmd_vhost_remove "$@";;
    db-clone)     [ $# -eq 2 ] || die "usage: db-clone <src> <dst>"; cmd_db_clone "$@";;
    db-drop)      [ $# -eq 1 ] || die "usage: db-drop <db>"; cmd_db_drop "$@";;
    phplog-purge) [ $# -eq 1 ] || die "usage: phplog-purge <basename>"; cmd_phplog_purge "$@";;
    *) die "verbe inconnu : ${verb:-<vide>} (vhost-add|vhost-remove|db-clone|db-drop|phplog-purge)";;
esac
