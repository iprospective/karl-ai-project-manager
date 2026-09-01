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
#   vhost-add <name> <docroot> <sock> [canonical]
#                                       crée+active le vhost Apache <name>.lxc.
#                                       <canonical> = domaine canonique de l'appli
#                                       (ps_shop_url pour PrestaShop) : le vhost pose
#                                       alors la réécriture anti-redirection (RM2813)
#   vhost-proxy-add <name> <port>       crée+active le vhost reverse proxy <name>.lxc
#                                       → http://127.0.0.1:<port>/ (envs portés par un
#                                       daemon HTTP — karl-agent, serveurs non-PHP ; RM2358)
#   vhost-karl-add <name> <port>        crée+active un vhost karl COMPLET <name>.lxc
#                                       (HTTPS + terminal wss /ttyd/ws, même conf que la
#                                       prod via karl-vhost-render ; RM2565) → instance
#                                       de TEST cockpit ; ttyd de prod partagé
#   vhost-remove <name>                 désactive+supprime (si géré par nous) + purge logs apache
#   db-clone <src> <dst> [motif ...]    CREATE DATABASE dst + copie (dst = *_rm<id> uniquement).
#                                       motifs LIKE optionnels = tables EXCLUES des données
#                                       (structure toujours copiée — logs, cache…)
#   db-post-sql <db>                    exécute le SQL lu sur STDIN dans <db> (*_rm<id> uniquement)
#                                       via un compte MySQL CONFINÉ à cette BDD (pas root :
#                                       le SQL du manifeste ne peut pas s'échapper du clone)
#   db-drop <db>                        DROP DATABASE (db = *_rm<id> uniquement)
#   phplog-purge <basename>             purge /var/log/php/<basename>.{error,slow}.log (basename *-rm<id>)
#   daemon-add <name> <port> <user> <workdir> <argv...>
#                                       pose+démarre l'unité systemd pm-env-<name>.service :
#                                       un DAEMON HTTP (serveur Python/Node…) écoutant sur
#                                       <port>, pour les envs que le vhost reverse-proxy sert
#                                       déjà (RM2693). L'unité est le pendant manquant de
#                                       vhost-proxy-add : sans elle, le vhost ne proxyfie rien.
#   daemon-remove <name>                arrête+désactive+supprime l'unité (si gérée par nous)
#   ws-init <workspace>                 crée/normalise le SQUELETTE d'un workspace projet
#                                       (racine, .mmi-pm/, repos/, envs/, tmp sessions logs
#                                       data) + le .gitignore de whitelist du repo -core,
#                                       sous une racine verrouillée 2750 pm:pm, puis
#                                       applique le modèle de perms (RM2909). Comble le trou
#                                       entre pm-project-new/pm-env-init et pm-perms.
#   ws-perms <workspace>                (ré)applique le modèle de perms — verbe symétrique,
#                                       à passer en fin de création. Idempotent.
#
# Garde-fous :
#   - vhost <name> : ^[a-z0-9_.-]+-(rm[0-9]+|dev|test)$ ; remove exige le marqueur
#     « managed-by: pm-env-helper » dans le .conf (jamais de vhost tiers).
#   - docroot : sous /home/workspaces/ (realpath), doit exister.
#   - sock : /run/php/<pool>.sock existant.
#   - BDD : clone/drop UNIQUEMENT des noms suffixés _rm<id> (une BDD partagée
#     n'est jamais droppable) ; clone refuse d'écraser une dst existante.
#   - daemon : c'est LE point sensible du verbe (RM2693) — une unité systemd exécute du code.
#     Trois barrières, dont la première suffit à elle seule à écarter l'escalade :
#       1. `user` DOIT être l'invocateur (`$SUDO_USER`) — on ne peut lancer un daemon que sous
#          SA PROPRE identité. Jamais root, jamais un autre compte. Un manifeste compromis ne
#          gagne donc RIEN : son auteur pouvait déjà exécuter ce code sans sudo.
#       2. l'exécutable (argv[0]) doit être un fichier exécutable RÉEL, résolu sous <workdir>,
#          lui-même sous $WS_ROOT. `/bin/sh -c '…'` est donc refusé : pas de shell interposé,
#          et systemd n'en ouvre pas non plus (ExecStart n'est pas passé à un shell).
#       3. chaque argument est validé caractère par caractère : ni saut de ligne (qui
#          injecterait une directive dans l'unité), ni `%` (spécificateur systemd).
#     L'unité est en outre durcie : NoNewPrivileges, PrivateTmp, ProtectSystem=full.
#     `post_create` du manifeste (recréer un venv…) N'EST PAS exécuté ici : c'est du shell
#     arbitraire, il reste côté pm-env-session, non privilégié, sous l'identité de l'user.
#   - configtest Apache avant reload, rollback si KO.
#   - workspace : chemin résolu par realpath, sous $WS_ROOT, profondeur EXACTE
#     <client>/<projet>, slug conforme ; refus de tout composant symlink (chmod/chown
#     déréférencent) ; refus d'adopter une racine existante qui n'appartient ni à `pm`
#     ni à l'invocateur. Le modèle (dossiers, modes, owners) N'EST PAS redéclaré ici :
#     il vient de pm-perms (--list-dirs / --apply), dont on vérifie qu'il est root-owned
#     et non modifiable hors root avant de l'exécuter en root.
#   - audit : chaque mutation est loguée dans syslog (logger -t pm-env-helper).

set -euo pipefail

MARKER="# managed-by: pm-env-helper"
WS_ROOT="/zfs/workspaces"
SITES="/etc/apache2/sites-available"
UNITS="/etc/systemd/system"
PORT_MIN=21000; PORT_MAX=21999      # même plage que le registre de pm-env-expose (RM2358)

die() { echo "pm-env-helper: $*" >&2; exit 1; }
audit() { logger -t pm-env-helper -- "$SUDO_USER: $*" || true; }

[ "$(id -u)" = 0 ] || die "doit tourner en root (via sudo)"

# Convention hostname (RM2358) : <project>-rm<id>[-s<seq>].lxc pour les envs de
# ticket (suffixe session optionnel), <project>-dev/-test pour les envs stables.
vname_ok()  { [[ "$1" =~ ^[a-z0-9_.-]+-(rm[0-9]+(-s[0-9]+)?|dev|test)$ ]]; }
dbname_ok() { [[ "$1" =~ ^[a-z0-9_]+$ ]]; }
db_ephemeral() { [[ "$1" =~ _rm[0-9]+$ ]]; }
db_exists() { mysql -NBe "SHOW DATABASES LIKE '$1'" | grep -qx "$1"; }
port_ok() { [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge "$PORT_MIN" ] && [ "$1" -le "$PORT_MAX" ]; }
# Un argument d'ExecStart ne doit ni casser le fichier d'unité (saut de ligne) ni se faire
# interpréter par systemd (`%` = spécificateur). Le reste passe : systemd n'ouvre pas de shell.
arg_ok() { [[ "$1" != *$'\n'* && "$1" != *$'\r'* && "$1" != *%* ]]; }

apache_apply() {
    # configtest puis reload ; en cas d'échec, exécute le rollback passé en argument.
    if ! apache2ctl configtest >/dev/null 2>&1; then
        eval "$1"
        die "apache configtest KO — modification annulée"
    fi
    systemctl reload apache2
}

# Anti-redirection canonique (RM2813) — envs de dev/recette servis sur un domaine
# alternatif tout en partageant la base d'un autre env.
#
# L'appli renvoie vers le domaine déclaré dans SA base : PrestaShop fait un 301 en
# front et un 302 vers AdminLogin en back-office. Les overrides PHP ne rattrapent
# que le front — le lien du back-office est produit par le routeur Symfony, qui les
# ignore. On corrige donc en sortie d'Apache, où tout passe quelle que soit la
# couche qui l'a émis.
#
# Sans le mot-clé `always` : le Location posé par PHP vit dans headers_out, pas dans
# err_headers_out. Avec `always`, la directive ne s'applique pas — vérifié dans les
# deux sens sur calicote-presta-rm2780.
#
# Chaque bloc est gardé par son <IfModule> : mod_substitute n'est pas activé
# partout, et son absence ne doit pas empêcher le vhost de se charger.
vhost_canonical_block() {
    local canon="$1" host="$2" canon_re
    canon_re=${canon//./\\.}
    cat <<EOF

    # Anti-redirection canonique (dev/recette, RM2813) : sans ceci, l'env renvoie
    # vers $canon et l'on quitte le worktree sans s'en apercevoir.
    <IfModule mod_headers.c>
        Header edit Location "^(https?://)$canon_re(/.*)?\$" "\$1$host\$2"
    </IfModule>
    <IfModule mod_substitute.c>
        AddOutputFilterByType SUBSTITUTE text/html
        Substitute "s|https?://$canon_re|http://$host|in"
    </IfModule>
EOF
}

cmd_vhost_add() {
    local name="$1" docroot="$2" sock="$3" canonical="${4:-}" conf real canon_block=""
    vname_ok "$name" || die "nom de vhost invalide : $name"
    real=$(realpath -e "$docroot" 2>/dev/null) || die "docroot introuvable : $docroot"
    [[ "$real" == "$WS_ROOT"/* ]] || die "docroot hors de $WS_ROOT : $real"
    [[ "$sock" =~ ^/run/php/[A-Za-z0-9_-]+\.sock$ ]] || die "sock invalide : $sock"
    [ -S "$sock" ] || die "sock inexistant : $sock"
    conf="$SITES/$name.conf"
    if [ -e "$conf" ]; then
        grep -qF "$MARKER" "$conf" || die "$name.conf existe et n'est pas géré par pm-env-helper"
    fi
    if [ -n "$canonical" ]; then
        [[ "$canonical" =~ ^[a-z0-9.-]+$ ]] || die "domaine canonique invalide : $canonical"
        # Un canonique égal à l'hôte servi (cas d'un env à base clonée, dont le
        # post_sql a déjà réécrit le domaine) n'a rien à réécrire.
        if [ "$canonical" != "$name.lxc" ]; then
            canon_block=$(vhost_canonical_block "$canonical" "$name.lxc")
        fi
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

$canon_block
    ErrorLog  \${APACHE_LOG_DIR}/$name.error.log
    CustomLog \${APACHE_LOG_DIR}/$name.access.log combined
</VirtualHost>
EOF
    a2ensite -q "$name" >/dev/null
    apache_apply "a2dissite -q '$name' >/dev/null; rm -f '$conf'"
    audit "vhost-add $name docroot=$real sock=$sock canonical=${canonical:-none}"
    echo "✓ vhost $name.lxc → $real (pool $(basename "$sock" .sock))${canon_block:+ · anti-redirection depuis $canonical}"
}

# Certificat TLS des vhosts .lxc de dev : snakeoil auto-signé (convention de
# l'instance — cf. calicote-*.lxc:443). Overridable via env pour une box qui
# aurait un wildcard dédié.
SSL_CERT="${PM_ENV_SSL_CERT:-/etc/ssl/certs/ssl-cert-snakeoil.pem}"
SSL_KEY="${PM_ENV_SSL_KEY:-/etc/ssl/private/ssl-cert-snakeoil.key}"

# Renderer du vhost karl (RM2565) : co-déployé à côté de ce helper par
# `mmi-pm core update` (source deploy/karl-agent/karl-vhost-render.sh). Source
# UNIQUE du template, partagée avec le vhost de prod (apache-vhost-setup.sh) →
# les vhosts de test cockpit ne divergent jamais de la conf déployée.
KARL_VHOST_RENDER="${PM_KARL_VHOST_RENDER:-/usr/local/sbin/karl-vhost-render}"

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

cmd_vhost_karl_add() {
    # Vhost karl-agent COMPLET (HTTPS + terminal wss même origine `/ttyd/ws`)
    # pour une instance de TEST cockpit (RM2565). Même forme que le déploiement
    # de prod — template rendu par le MÊME karl-vhost-render que
    # apache-vhost-setup.sh, donc jamais de divergence. HTTPS est REQUIS ici :
    # sans contexte sécurisé le micro (getUserMedia/Whisper) et le terminal (wss)
    # du cockpit sont cassés — c'est la raison d'être de ce verbe vs proxy-add.
    # ttyd PARTAGÉ avec la prod (`/ttyd/` → 127.0.0.1:7681) : PAS de listener
    # :7681 dédié ici (il vit dans karl.conf ; un `Listen` doublon casserait Apache).
    local name="$1" port="$2" conf
    vname_ok "$name" || die "nom de vhost invalide : $name"
    [[ "$port" =~ ^[0-9]+$ ]] && [ "$port" -ge 1024 ] && [ "$port" -le 65535 ] \
        || die "port invalide (1024-65535 attendu) : $port"
    [ -x "$KARL_VHOST_RENDER" ] || die "renderer karl absent : $KARL_VHOST_RENDER (mmi-pm core update requis pour le co-déployer)"
    { [ -r "$SSL_CERT" ] && [ -r "$SSL_KEY" ]; } \
        || die "cert TLS introuvable ($SSL_CERT) — le cockpit exige HTTPS (micro/terminal)"
    conf="$SITES/$name.conf"
    if [ -e "$conf" ]; then
        grep -qF "$MARKER" "$conf" || die "$name.conf existe et n'est pas géré par pm-env-helper"
    fi
    # managed-by commence par « pm-env-helper » → vhost-remove le reconnaît (MARKER).
    "$KARL_VHOST_RENDER" \
        --managed-by "pm-env-helper (karl-style, RM2565)" \
        --host "$name.lxc" --port "$port" \
        --ssl-cert "$SSL_CERT" --ssl-key "$SSL_KEY" \
        --log-prefix "$name" > "$conf"
    a2enmod -q proxy proxy_http proxy_wstunnel ssl >/dev/null 2>&1 || true
    a2ensite -q "$name" >/dev/null
    apache_apply "a2dissite -q '$name' >/dev/null; rm -f '$conf'"
    audit "vhost-karl-add $name port=$port"
    echo "✓ vhost karl $name.lxc → 127.0.0.1:$port (https + terminal wss /ttyd/ws, ttyd prod partagé)"
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
cmd_daemon_add() {
    local name="$1" port="$2" user="$3" workdir="$4"; shift 4
    local unit real exe a quoted=""
    vname_ok "$name" || die "nom de daemon invalide : $name"
    port_ok "$port" || die "port hors plage $PORT_MIN-$PORT_MAX : $port"
    # BARRIÈRE 1 — on ne lance un daemon que sous SA PROPRE identité.
    [ -n "${SUDO_USER:-}" ] || die "SUDO_USER absent : refus (invocation hors sudo ?)"
    [ "$user" = "$SUDO_USER" ] || die "user doit être l'invocateur ($SUDO_USER), pas « $user »"
    [ "$(id -u "$user" 2>/dev/null || echo 0)" != 0 ] || die "refus de lancer un daemon en root"
    real=$(realpath -e "$workdir" 2>/dev/null) || die "workdir introuvable : $workdir"
    [[ "$real" == "$WS_ROOT"/* ]] || die "workdir hors de $WS_ROOT : $real"
    [ $# -ge 1 ] || die "argv vide"
    # BARRIÈRE 2 — argv[0] est un exécutable réel SOUS le workdir. Interdit `/bin/sh -c …`.
    exe=$(realpath -e "$1" 2>/dev/null) || exe=$(realpath -e "$real/$1" 2>/dev/null) \
        || die "exécutable introuvable : $1"
    [[ "$exe" == "$real"/* ]] || die "exécutable hors du workdir : $exe"
    [ -f "$exe" ] && [ -x "$exe" ] || die "pas un exécutable : $exe"
    # BARRIÈRE 3 — chaque argument est validé, puis cité pour l'unité.
    quoted="\"$exe\""; shift
    for a in "$@"; do
        arg_ok "$a" || die "argument refusé (saut de ligne ou %) : $a"
        quoted="$quoted \"${a//\"/\\\"}\""
    done
    unit="$UNITS/pm-env-$name.service"
    if [ -e "$unit" ]; then
        grep -qF "$MARKER" "$unit" || die "$unit existe et n'est pas géré par pm-env-helper"
    fi
    cat > "$unit" <<EOF
$MARKER
[Unit]
Description=env de session $name — daemon HTTP (pm-env-helper, RM2693)
After=network.target

[Service]
Type=simple
User=$user
WorkingDirectory=$real
ExecStart=$quoted
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectControlGroups=true
ProtectKernelTunables=true

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now "pm-env-$name.service" >/dev/null 2>&1 \
        || { systemctl status --no-pager -l "pm-env-$name.service" >&2 || true
             die "le daemon n'a pas démarré (voir status ci-dessus)"; }
    audit "daemon-add $name port=$port user=$user workdir=$real"
    echo "pm-env-$name.service actif sur 127.0.0.1:$port"
}

cmd_daemon_remove() {
    local name="$1" unit
    vname_ok "$name" || die "nom de daemon invalide : $name"
    unit="$UNITS/pm-env-$name.service"
    if [ ! -e "$unit" ]; then
        echo "pm-env-$name.service absent — rien à faire"; return 0
    fi
    grep -qF "$MARKER" "$unit" || die "$unit n'est pas géré par pm-env-helper — refus"
    systemctl disable --now "pm-env-$name.service" >/dev/null 2>&1 || true
    rm -f "$unit"
    systemctl daemon-reload
    systemctl reset-failed "pm-env-$name.service" >/dev/null 2>&1 || true
    audit "daemon-remove $name"
    echo "pm-env-$name.service supprimé"
}

# ------------------------------------------------------ squelette workspace (RM2909)
#
# Trou comblé : le modèle de perms multi-user (RM2438 / T6 RM2502) verrouille la racine
# d'un workspace en `2750 pm:pm` — group `r-x`, PAS d'écriture (invariant
# anti-déstructuration, volontaire). Un dev du groupe `pm` n'y peut donc créer NI
# `.mmi-pm/`, NI `repos/`, NI `envs/`, NI les partagés du layout : `pm-project-new`
# (RM2228) et `pm-env-init` (RM1947) échouaient en `Permission denied`, encadrés à la
# main par deux `sudo` interactifs à chaque création de projet.
#
# Doctrine : le helper ne fait QUE ce que lui seul peut faire — créer sous une racine
# verrouillée, et chown vers `pm`. Le MODÈLE n'est pas redéclaré ici : la liste des
# dossiers vient de `pm-perms.py --list-dirs`, les modes et owners de
# `pm-perms.py --apply`. Le layout peut bouger sans qu'une ligne de ce shell change.
PM_CORE="/zfs/workspaces/.mmi-pm-core"
PM_PERMS="$PM_CORE/scripts/pm-perms.py"
PM_ENV_INIT="$PM_CORE/scripts/pm-env-init.py"

# Même slug que pm-project-new (refuse ".." : le premier caractère doit être alphanum).
ws_slug_ok() { [[ "$1" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; }

ws_resolve() {
    # Chemin canonique d'un workspace, ou mort. Mêmes exigences fail-closed que les
    # verbes existants, plus la profondeur : sous $WS_ROOT, EXACTEMENT
    # <client>/<projet>, les deux composants conformes au slug. `realpath -m` (la cible
    # peut ne pas exister encore) résout les liens en chemin : une cible symlinkée hors
    # de $WS_ROOT sort du préfixe et se fait refuser ici.
    local raw="${1:-}" real rest client proj
    [ -n "$raw" ] || die "workspace vide"
    [[ "$raw" == /* ]] || die "chemin de workspace non absolu : $raw"
    real=$(realpath -m -- "$raw" 2>/dev/null) || die "chemin de workspace invalide : $raw"
    [[ "$real" == "$WS_ROOT"/* ]] || die "workspace hors de $WS_ROOT : $real"
    rest="${real#"$WS_ROOT"/}"
    [[ "$rest" == */* && "$rest" != */*/* ]] \
        || die "profondeur invalide (attendu <client>/<projet>) : $rest"
    client="${rest%%/*}"; proj="${rest##*/}"
    ws_slug_ok "$client" || die "nom de client non conforme au slug : $client"
    ws_slug_ok "$proj"   || die "nom de projet non conforme au slug : $proj"
    printf '%s\n' "$real"
}

ws_no_symlink() {
    # `chmod`/`chown` DÉRÉFÉRENCENT : un composant du modèle qui serait un lien ferait
    # muter sa CIBLE. Cas réel à écarter : un `.mmi-pm` symlinké vers le core PROD
    # root-owned, qui se retrouverait chown pm.
    [ ! -L "$1" ] || die "$1 est un lien symbolique — refusé (la normalisation suivrait le lien)"
}

core_script_check() {
    # On s'apprête à exécuter du Python EN ROOT : le script ET sa chaîne de dossiers
    # doivent être root-owned et non modifiables par groupe/autres — sinon un membre du
    # groupe `pm` obtiendrait root par simple édition de fichier.
    local script="$1" p st owner mode
    [ -f "$script" ] || die "script du core introuvable : $script (core PROD absent ?)"
    for p in "$script" "$PM_CORE/scripts" "$PM_CORE"; do
        st=$(stat -c '%U %a' "$p") || die "stat impossible : $p"
        owner="${st%% *}"; mode="${st##* }"
        [ "$owner" = root ] || die "$p n'appartient pas à root ($owner) — exécution refusée"
        if (( 8#$mode & 0022 )); then
            die "$p est modifiable hors root (mode $mode) — exécution refusée"
        fi
    done
}

pm_perms_check() { core_script_check "$PM_PERMS"; }

ws_model_dirs() {
    # Le modèle vient de pm-perms, jamais dupliqué ici. Chaque entrée est RE-validée
    # avant de devenir un chemin : relative, sans `..`, alphabet restreint.
    local out rel
    pm_perms_check
    out=$(python3 "$PM_PERMS" --list-dirs 2>&1) || die \
        "pm-perms --list-dirs a échoué — core déployé trop ancien ? (sudo mmi-pm core update) : $out"
    while IFS= read -r rel; do
        if [ -z "$rel" ] || [ "$rel" = "." ]; then continue; fi
        [[ "$rel" =~ ^[A-Za-z0-9._-][A-Za-z0-9._/-]*$ ]] || die "chemin de modèle invalide : $rel"
        [[ "$rel" != *..* ]] || die "chemin de modèle invalide : $rel"
        printf '%s\n' "$rel"
    done <<< "$out"
}

ws_apply_perms() {
    # Verbe symétrique de la création : le modèle est posé par son outil de référence,
    # pas par un chmod maison. Idempotent.
    local ws="$1"
    pm_perms_check
    python3 "$PM_PERMS" --apply "$ws" || die "pm-perms --apply a échoué sur $ws"
    audit "ws-perms $ws"
}

cmd_ws_init() {
    local ws client_dir dirs rel p owner created=0
    [ -n "${SUDO_USER:-}" ] || die "SUDO_USER absent : refus (invocation hors sudo ?)"
    getent group pm  >/dev/null || die "groupe pm inexistant — modèle multi-user non provisionné"
    getent passwd pm >/dev/null || die "user pm inexistant — modèle multi-user non provisionné"
    ws=$(ws_resolve "$1")
    client_dir=$(dirname "$ws")

    ws_no_symlink "$client_dir"
    if [ ! -e "$client_dir" ]; then
        mkdir -- "$client_dir"
        chown pm:pm -- "$client_dir"
        chmod 2750 -- "$client_dir"
        audit "ws-init crée le dossier client $client_dir"
        echo "· dossier client créé : $client_dir"
    fi
    [ -d "$client_dir" ] || die "$client_dir existe et n'est pas un dossier"

    ws_no_symlink "$ws"
    if [ -e "$ws" ]; then
        [ -d "$ws" ] || die "$ws existe et n'est pas un dossier"
        # Pas d'adoption SILENCIEUSE d'un dossier tiers. Deux cas, et deux seulement :
        #  · owner `pm` — déjà au modèle, normalisation idempotente ;
        #  · owner = l'invocateur — le chown vers `pm` ne lui donne rien qu'il n'ait
        #    déjà (il pouvait écrire et chmod ce dossier sans aucun sudo). Même
        #    doctrine que `daemon-add` : la première barrière suffit à elle seule.
        # root, un autre dev, un compte de service → refus.
        owner=$(stat -c '%U' "$ws")
        [ "$owner" = pm ] || [ "$owner" = "$SUDO_USER" ] \
            || die "$ws appartient à « $owner » (ni pm, ni $SUDO_USER) — adoption refusée"
    else
        mkdir -- "$ws"
        created=1
    fi

    dirs=$(ws_model_dirs) || die "modèle de dossiers indisponible"
    while IFS= read -r rel; do
        p="$ws/$rel"
        ws_no_symlink "$p"
        if [ -e "$p" ]; then
            [ -d "$p" ] || die "$p existe et n'est pas un dossier"
        else
            mkdir -p -- "$p"
            echo "· créé $rel/"
        fi
    done <<< "$dirs"

    ws_seed_gitignore "$ws"
    ws_apply_perms "$ws"
    audit "ws-init $ws (racine créée: $created)"
    echo "✓ squelette workspace prêt : $ws"
}

ws_seed_gitignore() {
    # La racine du workspace EST le worktree du repo `-core` (modèle co-localisé RM2228)
    # et son `.gitignore` est la whitelist qui fait que seul `.mmi-pm/` est suivi. En
    # `2750`, créer une entrée à la racine est justement ce que le modèle réserve au
    # privilège — donc ce fichier fait partie du squelette, pas du contenu.
    # Le TEXTE vient de pm-env-init (--print-gitignore), jamais recopié ici.
    local ws="$1" gi="$ws/.gitignore" body
    [ ! -e "$gi" ] || return 0
    core_script_check "$PM_ENV_INIT"
    body=$(python3 "$PM_ENV_INIT" --print-gitignore 2>&1) \
        || die "pm-env-init --print-gitignore a échoué — core déployé trop ancien ? : $body"
    [ -n "$body" ] || die "pm-env-init --print-gitignore n'a rien émis"
    printf '%s\n' "$body" > "$gi"
    # Contenu = churn (group-writable) : structure privilégiée, contenu partagé. C'est
    # pm-env-init, non privilégié, qui rafraîchira ce fichier par la suite.
    chown pm:pm -- "$gi"
    chmod 664 -- "$gi"
    echo "· créé .gitignore (whitelist .mmi-pm/)"
}

cmd_ws_perms() {
    local ws
    ws=$(ws_resolve "$1")
    ws_no_symlink "$ws"
    [ -d "$ws" ] || die "workspace inexistant : $ws"
    ws_apply_perms "$ws"
    echo "✓ modèle de perms appliqué : $ws"
}

case "$verb" in
    vhost-add)    [ $# -eq 3 ] || die "usage: vhost-add <name> <docroot> <sock>"; cmd_vhost_add "$@";;
    vhost-proxy-add) [ $# -eq 2 ] || die "usage: vhost-proxy-add <name> <port>"; cmd_vhost_proxy_add "$@";;
    vhost-karl-add) [ $# -eq 2 ] || die "usage: vhost-karl-add <name> <port>"; cmd_vhost_karl_add "$@";;
    vhost-remove) [ $# -eq 1 ] || die "usage: vhost-remove <name>"; cmd_vhost_remove "$@";;
    db-clone)     [ $# -ge 2 ] || die "usage: db-clone <src> <dst> [motif-exclusion ...]"; cmd_db_clone "$@";;
    db-post-sql)  [ $# -eq 1 ] || die "usage: db-post-sql <db>  (SQL sur stdin)"; cmd_db_post_sql "$@";;
    db-drop)      [ $# -eq 1 ] || die "usage: db-drop <db>"; cmd_db_drop "$@";;
    phplog-purge) [ $# -eq 1 ] || die "usage: phplog-purge <basename>"; cmd_phplog_purge "$@";;
    daemon-add)   [ $# -ge 5 ] || die "usage: daemon-add <name> <port> <user> <workdir> <argv...>"; cmd_daemon_add "$@";;
    daemon-remove) [ $# -eq 1 ] || die "usage: daemon-remove <name>"; cmd_daemon_remove "$@";;
    ws-init)      [ $# -eq 1 ] || die "usage: ws-init <workspace>"; cmd_ws_init "$@";;
    ws-perms)     [ $# -eq 1 ] || die "usage: ws-perms <workspace>"; cmd_ws_perms "$@";;
    *) die "verbe inconnu : ${verb:-<vide>} (vhost-add|vhost-proxy-add|vhost-karl-add|vhost-remove|db-clone|db-post-sql|db-drop|phplog-purge|daemon-add|daemon-remove|ws-init|ws-perms)";;
esac
