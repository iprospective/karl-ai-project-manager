#!/usr/bin/env bash
# apache-vhost-setup.sh — vhost Apache du cockpit karl-agent (RM1873).
# Idempotent. À lancer EN ROOT dans le conteneur `dev` (ssh root@dev.lxc).
#
# Expose (HTTPS — RM2561) :
#   https://<KARL_WEB_HOST>/         → API + cockpit karl-agent (127.0.0.1:<KARL_AGENT_PORT>)
#   https://<KARL_WEB_HOST>/ttyd/ws  → WebSocket du terminal (wss://, 127.0.0.1:7681)
#   http://<KARL_WEB_HOST>/          → redirige (302) vers https://
#     (le cockpit calcule ces URL depuis location → aucun réglage
#      KARL_AGENT_TTYD_URL nécessaire ; ttyd et karl-agent restent en loopback,
#      seuls les proxys Apache sont exposés)
#
# Invariant (RM2146) : ttyd est writable — AUCUN chemin vers lui sans auth, local
# compris. `/ttyd` est gated par le cookie karl_session (validateur karl-ttyd-auth,
# le même que sur mmi). L'ancien port dédié :7681 (repli iframe) relayait ttyd SANS
# auth à tout le bridge LXC : il est supprimé, et sa suppression s'applique au
# prochain passage de ce script (Listen retiré → rechargement Apache).
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
# Portée réseau : DEUX accès coexistent (corrigé RM3156 — ce commentaire affirmait
# « pas d'exposition publique », faux depuis RM2700, et il fondait un raisonnement
# de sécurité) :
#   · le bridge LXC (10.0.3.0/24), local à la workstation ;
#   · l'exposition PUBLIQUE via le frontal mmi — https://karl.iprospective.fr/ (RM2700).
#
# ⚠ Le frontal RÉÉCRIT le Host en $HOST avant de transmettre. C'est pour cela que ce
# vhost, dont le ServerName est le nom LXC, répond aussi au trafic public — et il n'y
# a AUCUN ServerAlias à ajouter pour le nom public. Le diagnostic de RM3124 a perdu du
# temps sur cette fausse piste : une requête portant Host: karl.iprospective.fr tombe
# bien sur le vhost par défaut (404 sur /ttyd/), mais ce n'est pas ce Host-là qui
# arrive ici.
#
# Ce qui protège l'accès : l'authentification du cockpit, OBLIGATOIRE dès cette
# exposition — KARL_WEB_USER / KARL_WEB_PASS (Basic, RM2139), puis token d'appareil
# (RM2334), plus le cookie de session même-origine qui porte ce token à l'upgrade
# WebSocket de /ttyd (RM2700) — validé AUSSI sur ce vhost local depuis RM2146. karl-agent.py le dit déjà dans son en-tête : « requis
# dès que le cockpit est exposé au-delà du bridge local ».
# Vérifiable en deux commandes :
#   curl -s <hôte>/cockpit-config | grep auth_required   → true
#   curl -so /dev/null -w '%{http_code}' <hôte>/sessions → 401
#
# KARL_AGENT_TOKEN n'est PAS requis et n'est volontairement pas posé : c'est un secret
# partagé antérieur, qui donne un accès admin complet SANS identifier d'utilisateur
# (`mode: shared-token`, rétrocompatibilité). L'ajouter aujourd'hui serait une clé
# passe-partout de plus, pas un renforcement — les identifiants et le token d'appareil
# identifient qui agit et distinguent les rôles.
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

# IP du conteneur : sert seulement à vérifier que $HOST résout bien ici.
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

# ── Validateur du terminal (RM2146) ─────────────────────────────────────────
# Programme de la RewriteMap qui gate /ttyd. Posé ici AVANT la conf : un
# programme de RewriteMap absent empêche Apache de démarrer. `mmi-pm core update`
# le tient ensuite à jour (DEPLOYS de pm-core-update).
TTYD_AUTH="/usr/local/sbin/karl-ttyd-auth"
if ! { [ -f "$TTYD_AUTH" ] && cmp -s "$SELF_DIR/karl-ttyd-auth.py" "$TTYD_AUTH"; }; then
    install -o root -g root -m 755 "$SELF_DIR/karl-ttyd-auth.py" "$TTYD_AUTH"
    echo "✓ validateur terminal installé : $TTYD_AUTH"
fi

# ── Modules requis (idempotent) ─────────────────────────────────────────────
a2enmod -q proxy proxy_http proxy_wstunnel ssl rewrite >/dev/null

# ── Conf désirée ────────────────────────────────────────────────────────────
# Template FACTORISÉ (RM2565) : le corps du vhost est rendu par
# karl-vhost-render.sh, SOURCE UNIQUE partagée avec les vhosts d'instances de
# test cockpit (pm-env-helper vhost-karl-add) → prod et test ne divergent plus.
NEW="$(mktemp)"; trap 'rm -f "$NEW"' EXIT
"$SELF_DIR/karl-vhost-render.sh" \
    --managed-by "apache-vhost-setup.sh (karl-agent, RM1873)" \
    --host "$HOST" --port "$PORT" \
    --ssl-cert "$SSL_CERT" --ssl-key "$SSL_KEY" \
    --log-prefix karl --ttyd-auth "$TTYD_AUTH" > "$NEW"

# ── Application (seulement si changement) ───────────────────────────────────
if [ -f "$CONF" ] && cmp -s "$NEW" "$CONF"; then
    a2ensite -q karl >/dev/null 2>&1 || true
    apache2ctl configtest >/dev/null 2>&1 || die "configtest KO (conf inchangée mais invalide ?)"
    echo "· karl.conf déjà à jour (https://$HOST/ → :$PORT, ttyd wss /ttyd/ws gated) — rien à faire"
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
echo "✓ vhost $HOST actif : cockpit https://$HOST/ (→ 127.0.0.1:$PORT), terminal wss://$HOST/ttyd/ws (→ 127.0.0.1:7681, gated cookie), :80 → https"
echo "  ⚠ cert auto-signé : accepter l'avertissement du navigateur une fois pour https://$HOST/ — le terminal passe par la même origine, rien de plus à accepter"
echo "  · port :7681 dédié supprimé (RM2146) : ttyd n'est plus joignable qu'à travers /ttyd, authentifié"
