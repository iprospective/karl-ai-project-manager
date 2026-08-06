#!/usr/bin/env bash
# apache-vhost-setup.sh — vhost Apache du cockpit karl-agent (RM1873).
# Idempotent. À lancer EN ROOT dans le conteneur `dev` (ssh root@dev.lxc).
#
# Expose (HTTPS — RM2561) :
#   https://<KARL_WEB_HOST>/         → API + cockpit karl-agent (127.0.0.1:<KARL_AGENT_PORT>)
#   https://<KARL_WEB_HOST>/ttyd/ws  → WebSocket du terminal (wss://, 127.0.0.1:7681)
#   https://<KARL_WEB_HOST>:7681/    → même ttyd, port dédié (repli iframe seulement)
#   http://<KARL_WEB_HOST>/          → redirige (302) vers https://
#     (le cockpit calcule ces URL depuis location → aucun réglage
#      KARL_AGENT_TTYD_URL nécessaire ; ttyd et karl-agent restent en loopback,
#      seuls les proxys Apache sont exposés)
#
# Pourquoi HTTPS (RM2561) : le cockpit capture le micro via getUserMedia (dictée
# Whisper, RM2533) qui n'est autorisé qu'en contexte sécurisé — sur http:// le
# navigateur refuse l'accès micro. Cert auto-signé snakeoil par défaut (comme les
# autres vhosts .lxc/.local du conteneur) : le navigateur affiche un avertissement
# à accepter une fois par host:port.
#
# Pourquoi le WebSocket est en MÊME ORIGINE (/ttyd/ws) : le cert auto-signé ne
# vaut que pour le host:port dont on a accepté l'avertissement. Un wss:// vers
# :7681 échoue alors en silence — un WebSocket n'a pas d'interstitiel « continuer
# quand même », le terminal reste noir sans que rien ne le dise. Servi sous
# https://<HOST>/ttyd/ws, il réutilise l'exception déjà accordée au cockpit :
# une seule acceptation, plus de terminal mort après un changement de profil.
#
# Config : KARL_WEB_HOST dans le .env du repo PM (défaut karl.lxc — résolu par
# le dnsmasq de l'host vers ce conteneur). La ligne est ajoutée au .env si absente.
# Cert TLS surchargeable via KARL_SSL_CERT / KARL_SSL_KEY (défaut snakeoil).
#
# Portée réseau : le bridge LXC est local à la workstation (10.0.3.0/24) — pas
# d'exposition publique. Si le bridge devait être partagé, poser KARL_AGENT_TOKEN
# (auth de l'API) avant d'élargir.
#
# Idempotence : modules/enable à blanc si déjà faits ; le .conf n'est réécrit
# (et Apache rechargé) que si le contenu généré change ; configtest avant
# reload avec restauration de l'ancienne conf en cas d'échec.
set -euo pipefail

die() { echo "apache-vhost-setup: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "à lancer en root (ssh root@dev.lxc)"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SELF_DIR/../.." && pwd)"
ENV_FILE="$REPO/.env"
CONF="/etc/apache2/sites-available/karl.conf"

# ── Config depuis .env (host DNS + port API) ────────────────────────────────
HOST=""
PORT="9876"
if [ -f "$ENV_FILE" ]; then
    HOST="$(grep -E '^KARL_WEB_HOST=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"' || true)"
    PORT="$(grep -E '^KARL_AGENT_PORT=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"' || true)"
    PORT="${PORT:-9876}"
fi
if [ -z "$HOST" ]; then
    HOST="karl.lxc"
    if [ -f "$ENV_FILE" ]; then
        printf '\n# Nom DNS du cockpit karl-agent (vhost Apache — deploy/karl-agent/apache-vhost-setup.sh)\nKARL_WEB_HOST=%s\n' "$HOST" >> "$ENV_FILE"
        echo "✓ KARL_WEB_HOST=$HOST ajouté à $ENV_FILE"
    else
        echo "  ⚠ $ENV_FILE absent — KARL_WEB_HOST non persisté (défaut $HOST)" >&2
    fi
fi
[[ "$HOST" =~ ^[a-z0-9.-]+$ ]] || die "KARL_WEB_HOST invalide : $HOST"

# IP du conteneur pour le listener 7681 (ttyd n'écoute qu'en loopback ; Apache
# écoute sur l'IP du bridge, pas de collision). Recalculée à chaque run →
# le script se ré-applique tout seul si l'IP du conteneur change.
IP="$(hostname -I | awk '{print $1}')"
[[ "$IP" =~ ^[0-9.]+$ ]] || die "IP conteneur introuvable (hostname -I : $IP)"
RESOLVED="$(getent hosts "$HOST" | awk '{print $1}' | head -1 || true)"
[ -n "$RESOLVED" ] && [ "$RESOLVED" != "$IP" ] && \
    echo "  ⚠ $HOST résout vers $RESOLVED mais le conteneur est $IP — vérifier dnsmasq" >&2

# ── Certificat TLS (RM2561) ─────────────────────────────────────────────────
# Auto-signé snakeoil par défaut (paquet ssl-cert), comme les autres vhosts
# .lxc/.local du conteneur. Surchargeable (KARL_SSL_CERT/KARL_SSL_KEY) si un
# vrai cert existe. On vérifie leur présence : root peut lire la clé privée.
SSL_CERT="${KARL_SSL_CERT:-/etc/ssl/certs/ssl-cert-snakeoil.pem}"
SSL_KEY="${KARL_SSL_KEY:-/etc/ssl/private/ssl-cert-snakeoil.key}"
[ -f "$SSL_CERT" ] || die "cert TLS introuvable : $SSL_CERT (installer le paquet ssl-cert ?)"
[ -f "$SSL_KEY" ]  || die "clé TLS introuvable : $SSL_KEY"

# ── Modules requis (idempotent) ─────────────────────────────────────────────
a2enmod -q proxy proxy_http proxy_wstunnel ssl >/dev/null

# ── Conf désirée ────────────────────────────────────────────────────────────
NEW="$(mktemp)"; trap 'rm -f "$NEW"' EXIT
cat > "$NEW" <<EOF
# managed-by: apache-vhost-setup.sh (karl-agent, RM1873) — NE PAS ÉDITER (régénéré)
#
# HTTPS obligatoire (RM2561) : getUserMedia (micro, dictée Whisper RM2533) exige
# un contexte sécurisé — http:// refuse le micro. Cert auto-signé snakeoil.

# :80 → redirection vers HTTPS (302 temporaire : évite un cache navigateur collant
# si l'on revient un jour en http, contrairement au 301 permanent).
<VirtualHost *:80>
    ServerName $HOST
    Redirect temp / https://$HOST/

    ErrorLog  \${APACHE_LOG_DIR}/karl.error.log
    CustomLog \${APACHE_LOG_DIR}/karl.access.log combined
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

    ErrorLog  \${APACHE_LOG_DIR}/karl.error.log
    CustomLog \${APACHE_LOG_DIR}/karl-ssl.access.log combined
</VirtualHost>

# Port dédié ttyd — conservé pour le SEUL repli iframe du cockpit (bundle
# xterm.js non chargé : le cockpit affiche alors l'UI ttyd native, qui exige la
# racine du serveur ttyd — elle fetch « /token » en absolu, donc ne survit pas au
# préfixe /ttyd/). Le chemin normal (client maison karl-term.js) passe par le
# vhost :443 ci-dessus et n'a plus besoin de ce port.
# ⚠ cert auto-signé propre à ce host:port → ce repli-là demande sa propre
# acceptation sur https://$HOST:7681/.
Listen $IP:7681
<VirtualHost $IP:7681>
    ServerName $HOST

    SSLEngine on
    SSLCertificateFile    $SSL_CERT
    SSLCertificateKeyFile $SSL_KEY

    ProxyPreserveHost On
    ProxyPass        /ws ws://127.0.0.1:7681/ws retry=0
    ProxyPassReverse /ws ws://127.0.0.1:7681/ws
    ProxyPass        / http://127.0.0.1:7681/ retry=0
    ProxyPassReverse / http://127.0.0.1:7681/

    ErrorLog  \${APACHE_LOG_DIR}/karl-ttyd.error.log
    CustomLog \${APACHE_LOG_DIR}/karl-ttyd.access.log combined
</VirtualHost>
EOF

# ── Application (seulement si changement) ───────────────────────────────────
if [ -f "$CONF" ] && cmp -s "$NEW" "$CONF"; then
    a2ensite -q karl >/dev/null 2>&1 || true
    apache2ctl configtest >/dev/null 2>&1 || die "configtest KO (conf inchangée mais invalide ?)"
    echo "· karl.conf déjà à jour (https://$HOST/ → :$PORT, ttyd wss /ttyd/ws + $IP:7681) — rien à faire"
    exit 0
fi

OLD=""
[ -f "$CONF" ] && OLD="$(mktemp)" && cp "$CONF" "$OLD"
install -m 644 "$NEW" "$CONF"
a2ensite -q karl >/dev/null
if ! apache2ctl configtest >/dev/null 2>&1; then
    if [ -n "$OLD" ]; then cp "$OLD" "$CONF"; else a2dissite -q karl >/dev/null; rm -f "$CONF"; fi
    apache2ctl configtest >/dev/null 2>&1 || true
    die "configtest KO — conf précédente restaurée"
fi
systemctl reload apache2
[ -n "$OLD" ] && rm -f "$OLD"
echo "✓ vhost $HOST actif : cockpit https://$HOST/ (→ 127.0.0.1:$PORT), terminal wss://$HOST/ttyd/ws (→ 127.0.0.1:7681), :80 → https"
echo "  ⚠ cert auto-signé : accepter l'avertissement du navigateur une fois pour https://$HOST/ — le terminal passe par la même origine, rien de plus à accepter"
echo "  · port :7681 conservé pour le repli iframe (cert à accepter séparément si ce repli est utilisé)"
