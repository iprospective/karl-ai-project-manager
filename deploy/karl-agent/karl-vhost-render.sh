#!/usr/bin/env bash
# karl-vhost-render.sh — générateur (stdout) du vhost Apache du cockpit karl-agent.
#
# SOURCE UNIQUE du template (RM2565) : émet la conf Apache HTTPS du cockpit
# (redirect :80→:443, SSL, terminal ttyd en même origine `/ttyd/ws`). Réutilisé
# par DEUX appelants pour qu'ils ne divergent JAMAIS :
#   - deploy/karl-agent/apache-vhost-setup.sh  → le vhost de PROD (karl.conf),
#     avec --ttyd-listen <IP> (listener :7681 dédié pour le repli iframe).
#   - pm-env-helper vhost-karl-add             → un vhost d'instance de TEST
#     cockpit, SANS --ttyd-listen : le terminal réutilise le ttyd de prod
#     partagé (`/ttyd/` → 127.0.0.1:7681), donc pas de second listener :7681
#     (il vit déjà dans karl.conf ; un doublon casserait `Listen`).
#
# N'écrit rien et n'exige AUCUN privilège : rend sur stdout, l'appelant applique.
#
# Usage :
#   karl-vhost-render.sh --managed-by TXT --host HOST --port PORT \
#       --ssl-cert CERT --ssl-key KEY --log-prefix PREFIX [--ttyd-listen IP]
#
# Le fichier reste identique au byte près à karl.conf quand il est appelé avec
# les paramètres de prod (garde de non-régression, cf. RM2565).
set -euo pipefail

MANAGED_BY="" HOST="" PORT="" SSL_CERT="" SSL_KEY="" LOG_PREFIX="" TTYD_LISTEN=""
while [ $# -gt 0 ]; do
    case "$1" in
        --managed-by)  MANAGED_BY="${2:-}"; shift 2;;
        --host)        HOST="${2:-}"; shift 2;;
        --port)        PORT="${2:-}"; shift 2;;
        --ssl-cert)    SSL_CERT="${2:-}"; shift 2;;
        --ssl-key)     SSL_KEY="${2:-}"; shift 2;;
        --log-prefix)  LOG_PREFIX="${2:-}"; shift 2;;
        --ttyd-listen) TTYD_LISTEN="${2:-}"; shift 2;;
        *) echo "karl-vhost-render: option inconnue : $1" >&2; exit 2;;
    esac
done

req() { [ -n "$2" ] || { echo "karl-vhost-render: $1 requis" >&2; exit 2; }; }
req --managed-by "$MANAGED_BY"
req --host       "$HOST"
req --port       "$PORT"
req --ssl-cert   "$SSL_CERT"
req --ssl-key    "$SSL_KEY"
req --log-prefix "$LOG_PREFIX"

# ── Bloc principal : redirect :80→:443 + vhost :443 (cockpit + terminal wss) ──
cat <<EOF
# managed-by: $MANAGED_BY — NE PAS ÉDITER (régénéré)
#
# HTTPS obligatoire (RM2561) : getUserMedia (micro, dictée Whisper RM2533) exige
# un contexte sécurisé — http:// refuse le micro. Cert auto-signé snakeoil.

# :80 → redirection vers HTTPS (302 temporaire : évite un cache navigateur collant
# si l'on revient un jour en http, contrairement au 301 permanent).
<VirtualHost *:80>
    ServerName $HOST
    Redirect temp / https://$HOST/

    ErrorLog  \${APACHE_LOG_DIR}/$LOG_PREFIX.error.log
    CustomLog \${APACHE_LOG_DIR}/$LOG_PREFIX.access.log combined
</VirtualHost>

<VirtualHost *:443>
    ServerName $HOST

    SSLEngine on
    SSLCertificateFile    $SSL_CERT
    SSLCertificateKeyFile $SSL_KEY

    ProxyPreserveHost On
    # Terminal (RM2561) : ttyd en même origine que le cockpit → le wss réutilise
    # l'exception de cert déjà accordée ici. Les règles spécifiques d'abord :
    # Apache retient le PREMIER ProxyPass qui matche, et « / » matche tout.
    ProxyPass        /ttyd/ws ws://127.0.0.1:7681/ws retry=0
    ProxyPassReverse /ttyd/ws ws://127.0.0.1:7681/ws
    ProxyPass        /ttyd/   http://127.0.0.1:7681/ retry=0
    ProxyPassReverse /ttyd/   http://127.0.0.1:7681/
    ProxyPass        /        http://127.0.0.1:$PORT/ retry=0
    ProxyPassReverse /        http://127.0.0.1:$PORT/

    ErrorLog  \${APACHE_LOG_DIR}/$LOG_PREFIX.error.log
    CustomLog \${APACHE_LOG_DIR}/$LOG_PREFIX-ssl.access.log combined
</VirtualHost>
EOF

# ── Listener :7681 dédié — PROD uniquement (repli iframe). Omis pour un vhost de
#    test : celui-ci partage le ttyd de prod via /ttyd/, sans redéclarer Listen. ─
[ -n "$TTYD_LISTEN" ] || exit 0
cat <<EOF

# Port dédié ttyd — conservé pour le SEUL repli iframe du cockpit (bundle
# xterm.js non chargé : le cockpit affiche alors l'UI ttyd native, qui exige la
# racine du serveur ttyd — elle fetch « /token » en absolu, donc ne survit pas au
# préfixe /ttyd/). Le chemin normal (client maison karl-term.js) passe par le
# vhost :443 ci-dessus et n'a plus besoin de ce port.
# ⚠ cert auto-signé propre à ce host:port → ce repli-là demande sa propre
# acceptation sur https://$HOST:7681/.
Listen $TTYD_LISTEN:7681
<VirtualHost $TTYD_LISTEN:7681>
    ServerName $HOST

    SSLEngine on
    SSLCertificateFile    $SSL_CERT
    SSLCertificateKeyFile $SSL_KEY

    ProxyPreserveHost On
    ProxyPass        /ws ws://127.0.0.1:7681/ws retry=0
    ProxyPassReverse /ws ws://127.0.0.1:7681/ws
    ProxyPass        / http://127.0.0.1:7681/ retry=0
    ProxyPassReverse / http://127.0.0.1:7681/

    ErrorLog  \${APACHE_LOG_DIR}/$LOG_PREFIX-ttyd.error.log
    CustomLog \${APACHE_LOG_DIR}/$LOG_PREFIX-ttyd.access.log combined
</VirtualHost>
EOF
