#!/usr/bin/env bash
# karl-vhost-render.sh — générateur (stdout) du vhost Apache du cockpit karl-agent.
#
# SOURCE UNIQUE du template (RM2565) : émet la conf Apache HTTPS du cockpit
# (redirect :80→:443, SSL, terminal ttyd en même origine `/ttyd/ws`). Réutilisé
# par DEUX appelants pour qu'ils ne divergent JAMAIS :
#   - deploy/karl-agent/apache-vhost-setup.sh  → le vhost de PROD (karl.conf) ;
#   - pm-env-helper vhost-karl-add             → un vhost d'instance de TEST
#     cockpit : le terminal réutilise le ttyd de prod partagé
#     (`/ttyd/` → 127.0.0.1:7681).
#
# Invariant (RM2146) : ttyd est writable (`-W`) — un accès = un shell. AUCUN
# chemin vers lui sans authentification, local compris. `/ttyd` est donc gated
# par le cookie `karl_session`, validé par karl-ttyd-auth auprès du karl-agent
# de l'instance (`--port`) — le même validateur que le vhost public mmi (RM2700).
# Fail-closed : validateur absent, karl-agent muet, cookie absent/invalide → 403.
# L'ancien vhost dédié :7681 (repli iframe, ouvert SANS auth sur le bridge LXC)
# est supprimé : `--ttyd-listen` est refusé plutôt qu'ignoré, pour qu'un
# appelant resté sur l'ancien contrat échoue au lieu de rouvrir le port.
#
# N'écrit rien et n'exige AUCUN privilège : rend sur stdout, l'appelant applique.
#
# Usage :
#   karl-vhost-render.sh --managed-by TXT --host HOST --port PORT \
#       --ssl-cert CERT --ssl-key KEY --log-prefix PREFIX [--ttyd-auth PATH]
#
# --ttyd-auth : chemin du validateur (défaut /usr/local/sbin/karl-ttyd-auth,
# co-déployé par `mmi-pm core update`). L'appelant vérifie sa présence : un
# programme de RewriteMap manquant empêche Apache de démarrer.
set -euo pipefail

MANAGED_BY="" HOST="" PORT="" SSL_CERT="" SSL_KEY="" LOG_PREFIX="" TTYD_AUTH="/usr/local/sbin/karl-ttyd-auth"
while [ $# -gt 0 ]; do
    case "$1" in
        --managed-by)  MANAGED_BY="${2:-}"; shift 2;;
        --host)        HOST="${2:-}"; shift 2;;
        --port)        PORT="${2:-}"; shift 2;;
        --ssl-cert)    SSL_CERT="${2:-}"; shift 2;;
        --ssl-key)     SSL_KEY="${2:-}"; shift 2;;
        --log-prefix)  LOG_PREFIX="${2:-}"; shift 2;;
        --ttyd-auth)   TTYD_AUTH="${2:-}"; shift 2;;
        --ttyd-listen) echo "karl-vhost-render: --ttyd-listen retiré (RM2146) : le vhost :7681 exposait ttyd sans auth" >&2; exit 2;;
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
req --ttyd-auth  "$TTYD_AUTH"
[[ "$PORT" =~ ^[0-9]+$ ]] || { echo "karl-vhost-render: --port numérique attendu : $PORT" >&2; exit 2; }

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
    # Terminal GATED (RM2146) : ttyd writable = un shell. Le cookie karl_session
    # (posé par le cockpit depuis le token d'appareil, RM2700) est validé auprès
    # du karl-agent de CETTE instance ; tout autre cas → 403, avant le proxy.
    RewriteEngine On
    RewriteMap karlauth "prg:$TTYD_AUTH --verify-url http://127.0.0.1:$PORT/api/auth/whoami"
    RewriteCond "\${karlauth:%{HTTP:Cookie}}" "!=OK"
    RewriteRule "^/ttyd(/|\$)" "-" [F]
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
