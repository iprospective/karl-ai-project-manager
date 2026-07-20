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
#   vhost-proxy-add <name> <port>       crée+active le vhost reverse proxy <name>.lxc
#                                       → http://127.0.0.1:<port>/ (envs portés par un
#                                       daemon HTTP — karl-agent, serveurs non-PHP ; RM2358)
#   vhost-remove <name>                 désactive+supprime (si géré par nous) + purge logs apache
#   db-clone <src> <dst> [motif ...]    CREATE DATABASE dst + copie (dst = *_rm<id> uniquement).
#                                       motifs LIKE optionnels = tables EXCLUES des données
#                                       (structure toujours copiée — logs, cache…)
#   db-post-sql <db>                    exécute le SQL lu sur STDIN dans <db> (*_rm<id> uniquement)
#                                       via un compte MySQL CONFINÉ à cette BDD (pas root :
#                                       le SQL du manifeste ne peut pas s'échapper du clone)
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

# Convention hostname (RM2358) : <project>-rm<id>[-s<seq>].lxc pour les envs de
# ticket (suffixe session optionnel), <project>-dev/-test pour les envs stables.
vname_ok()  { [[ "$1" =~ ^[a-z0-9_.-]+-(rm[0-9]+(-s[0-9]+)?|dev|test)$ ]]; }
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

# Certificat TLS des vhosts .lxc de dev : snakeoil auto-signé (convention de
# l'instance — cf. calicote-*.lxc:443). Overridable via env pour une box qui
# aurait un wildcard dédié.
SSL_CERT="${PM_ENV_SSL_CERT:-/etc/ssl/certs/ssl-cert-snakeoil.pem}"
SSL_KEY="${PM_ENV_SSL_KEY:-/etc/ssl/private/ssl-cert-snakeoil.key}"

cmd_vhost_proxy_add() {
    # Vhost reverse proxy <name>.lxc → http://127.0.0.1:<port>/ (RM2358).
    # Pour les envs servis par un daemon HTTP en loopback (karl-agent, serveurs
    # de dev non-PHP). SSE ok via proxy_http ; WebSocket : ajouter un vhost
    # dédié si besoin (cf. deploy/karl-agent/apache-vhost-setup.sh, ttyd).
    # Émet :80 ET :443 (RM2358 corr.) : les navigateurs accèdent aux .lxc en
    # HTTPS (d'autres .lxc de l'instance ont du SSL) → sans le vhost :443, la
    # requête tombait sur le vhost SSL par défaut (« Apache2 Ubuntu Default
    # Page »). Le :443 réutilise le cert snakeoil (dev local — avertissement de
    # cert attendu, comme les autres .lxc).
    local name="$1" port="$2" conf ssl_block=""
    vname_ok "$name" || die "nom de vhost invalide : $name"
    [[ "$port" =~ ^[0-9]+$ ]] && [ "$port" -ge 1024 ] && [ "$port" -le 65535 ] \
        || die "port invalide (1024-65535 attendu) : $port"
    conf="$SITES/$name.conf"
    if [ -e "$conf" ]; then
        grep -qF "$MARKER" "$conf" || die "$name.conf existe et n'est pas géré par pm-env-helper"
    fi
    # Le :443 n'est émis que si le cert existe (fail-safe : sinon configtest KO
    # casserait Apache — on se rabat sur :80 seul avec un avertissement).
    if [ -r "$SSL_CERT" ] && [ -r "$SSL_KEY" ]; then
        ssl_block="$(cat <<EOF

<VirtualHost *:443>
    ServerName $name.lxc

    SSLEngine on
    SSLCertificateFile    $SSL_CERT
    SSLCertificateKeyFile $SSL_KEY

    ProxyPreserveHost On
    ProxyPass        / http://127.0.0.1:$port/ retry=0
    ProxyPassReverse / http://127.0.0.1:$port/

    ErrorLog  \${APACHE_LOG_DIR}/$name.error.log
    CustomLog \${APACHE_LOG_DIR}/$name.access.log combined
</VirtualHost>
EOF
)"
    else
        echo "  ⚠ cert TLS introuvable ($SSL_CERT) — vhost :443 non généré (HTTP seul)" >&2
    fi
    cat > "$conf" <<EOF
$MARKER
<VirtualHost *:80>
    ServerName $name.lxc

    ProxyPreserveHost On
    ProxyPass        / http://127.0.0.1:$port/ retry=0
    ProxyPassReverse / http://127.0.0.1:$port/

    ErrorLog  \${APACHE_LOG_DIR}/$name.error.log
    CustomLog \${APACHE_LOG_DIR}/$name.access.log combined
</VirtualHost>
$ssl_block
EOF
    a2enmod -q proxy proxy_http >/dev/null 2>&1 || true
    [ -n "$ssl_block" ] && a2enmod -q ssl >/dev/null 2>&1 || true
    a2ensite -q "$name" >/dev/null
    apache_apply "a2dissite -q '$name' >/dev/null; rm -f '$conf'"
    audit "vhost-proxy-add $name port=$port ssl=$([ -n "$ssl_block" ] && echo 1 || echo 0)"
    echo "✓ vhost $name.lxc → 127.0.0.1:$port (reverse proxy$([ -n "$ssl_block" ] && echo ', http+https' || echo ', http'))"
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
    local src="$1" dst="$2"; shift 2
    dbname_ok "$src" || die "nom de BDD source invalide : $src"
    dbname_ok "$dst" || die "nom de BDD cible invalide : $dst"
    db_ephemeral "$dst" || die "cible non éphémère ($dst) : un clone doit être suffixé _rm<id>"
    db_exists "$src" || die "BDD source inexistante : $src"
    db_exists "$dst" && die "BDD cible existe déjà : $dst (db-drop d'abord si voulu)"

    # motifs LIKE de tables à exclure des DONNÉES (structure toujours copiée)
    local pat excluded=() ignore_args=() t
    for pat in "$@"; do
        [[ "$pat" =~ ^[A-Za-z0-9_%]+$ ]] || die "motif d'exclusion invalide : $pat"
        while IFS= read -r t; do
            excluded+=("$t"); ignore_args+=("--ignore-table=$src.$t")
        done < <(mysql -NBe "SELECT table_name FROM information_schema.tables
                             WHERE table_schema = '$src' AND table_type = 'BASE TABLE'
                               AND table_name LIKE '$pat'")
    done

    mysql -e "CREATE DATABASE \`$dst\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    # passe 1 : structure complète (toutes tables, vues, routines, triggers)
    # passe 2 : données, moins les tables exclues
    if ! { mysqldump --single-transaction --no-data --routines --triggers "$src" | mysql "$dst" \
           && mysqldump --single-transaction --no-create-info --skip-triggers \
                        "${ignore_args[@]}" "$src" | mysql "$dst"; }; then
        mysql -e "DROP DATABASE IF EXISTS \`$dst\`"
        die "copie $src → $dst échouée — clone annulé"
    fi
    # mêmes droits que la source pour les comptes applicatifs
    mysql -NBe "SELECT CONCAT('GRANT ALL PRIVILEGES ON \`$dst\`.* TO ''', User, '''@''', Host, ''';')
                FROM mysql.db WHERE Db = '$src' AND User <> ''" | mysql || true
    mysql -e "FLUSH PRIVILEGES"
    audit "db-clone $src → $dst (exclusions: ${#excluded[@]})"
    echo "✓ BDD $dst clonée depuis $src"
    [ ${#excluded[@]} -gt 0 ] && \
        echo "  (${#excluded[@]} table(s) copiée(s) SANS données : ${excluded[*]})"
    return 0
}

EXEC_CNF="/root/.pm-env-exec.cnf"
EXEC_USER="pm_env_exec"

ensure_exec_account() {
    # Compte MySQL CONFINÉ pour le SQL fourni par les manifestes : aucun droit
    # global, grants posés BDD par BDD → le SQL ne peut pas sortir du clone.
    if [ ! -f "$EXEC_CNF" ]; then
        local pw
        pw=$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)
        mysql -e "CREATE USER IF NOT EXISTS '$EXEC_USER'@'localhost' IDENTIFIED BY '$pw';
                  ALTER USER '$EXEC_USER'@'localhost' IDENTIFIED BY '$pw'"
        umask 077
        printf '[client]\nuser = %s\npassword = %s\n' "$EXEC_USER" "$pw" > "$EXEC_CNF"
    fi
}

cmd_db_post_sql() {
    local db="$1"
    dbname_ok "$db" || die "nom de BDD invalide : $db"
    db_ephemeral "$db" || die "refus : $db n'est pas une BDD éphémère (_rm<id>)"
    db_exists "$db" || die "BDD inexistante : $db"
    ensure_exec_account
    mysql -e "GRANT ALL PRIVILEGES ON \`$db\`.* TO '$EXEC_USER'@'localhost'; FLUSH PRIVILEGES"
    # exécution CONFINÉE : compte sans privilège global → USE/écriture hors $db refusés
    if ! mysql --defaults-extra-file="$EXEC_CNF" "$db"; then
        die "post-SQL en échec dans $db (le clone reste en l'état — corriger le manifeste ou db-drop)"
    fi
    audit "db-post-sql $db"
    echo "✓ post-SQL appliqué sur $db"
}

cmd_db_drop() {
    local db="$1"
    dbname_ok "$db" || die "nom de BDD invalide : $db"
    db_ephemeral "$db" || die "refus : $db n'est pas une BDD éphémère (_rm<id>)"
    db_exists "$db" || { echo "· BDD $db absente — rien à faire"; return 0; }
    mysql -e "DROP DATABASE \`$db\`"
    # DROP DATABASE ne purge pas les grants par-BDD (posés par db-clone) → orphelins
    mysql -e "DELETE FROM mysql.db WHERE Db = '$db'; FLUSH PRIVILEGES"
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
    vhost-proxy-add) [ $# -eq 2 ] || die "usage: vhost-proxy-add <name> <port>"; cmd_vhost_proxy_add "$@";;
    vhost-remove) [ $# -eq 1 ] || die "usage: vhost-remove <name>"; cmd_vhost_remove "$@";;
    db-clone)     [ $# -ge 2 ] || die "usage: db-clone <src> <dst> [motif-exclusion ...]"; cmd_db_clone "$@";;
    db-post-sql)  [ $# -eq 1 ] || die "usage: db-post-sql <db>  (SQL sur stdin)"; cmd_db_post_sql "$@";;
    db-drop)      [ $# -eq 1 ] || die "usage: db-drop <db>"; cmd_db_drop "$@";;
    phplog-purge) [ $# -eq 1 ] || die "usage: phplog-purge <basename>"; cmd_phplog_purge "$@";;
    *) die "verbe inconnu : ${verb:-<vide>} (vhost-add|vhost-proxy-add|vhost-remove|db-clone|db-post-sql|db-drop|phplog-purge)";;
esac
