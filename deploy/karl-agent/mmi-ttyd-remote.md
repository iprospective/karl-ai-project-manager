# Terminal karl distant — exposition `/ttyd` sur `karl.iprospective.fr` (RM2700)

Spec de coupure **PROD (mmi)** — à appliquer sous **feu vert humain**. Rend le
terminal du cockpit joignable à distance, en **même origine** (`/ttyd/ws`),
**gated** par le cookie de session karl (approche A, RM2334/RM2700).

Rappel archi : le public passe par le tunnel reverse `autossh` de
`karl-agent-tunnel.service` (dev.lxc → `mmi:127.0.0.1:9876`). Le cockpit vise
déjà `location.origin + "/ttyd"` → **aucun changement cockpit**. Le token du
terminal est dans la 1re frame ttyd (invisible à l'upgrade), donc le gate se
fait sur le **cookie même-origine** validé en loopback via `/auth/whoami`.

## 1. Étendre le tunnel (dev.lxc) — acheminer le port ttyd

`~/.config/systemd/user/karl-agent-tunnel.service`, ajouter un second `-R`
(bind DISTANT explicitement en `127.0.0.1`, comme l'existant — jamais `-R 7681:`
seul, cf. GatewayPorts) :

    -R 127.0.0.1:9876:127.0.0.1:9876 \
    -R 127.0.0.1:7681:127.0.0.1:7681 mmi

Puis : `systemctl --user daemon-reload && systemctl --user restart karl-agent-tunnel`
Vérif depuis mmi : `curl -sI http://127.0.0.1:7681/ | head -1` (ttyd répond).

## 2. Déployer le validateur de cookie (mmi, root)

    install -o root -g root -m 755 \
      deploy/karl-agent/karl-ttyd-auth.py /usr/local/sbin/karl-ttyd-auth

Test hors Apache (doit rendre OK avec un vrai cookie, DENY sinon) :

    KARL_VERIFY_URL=http://127.0.0.1:9876/auth/whoami \
      /usr/local/sbin/karl-ttyd-auth --check 'karl_session=<token-valide>'

## 3. Modules Apache (mmi)

    a2enmod proxy proxy_http proxy_wstunnel rewrite headers
    systemctl reload apache2   # après le §4

## 4. Vhost `karl.iprospective.fr` (mmi) — ajouts dans le `<VirtualHost *:443>`

    # RewriteMap DOIT être en contexte vhost (pas dans <Location>).
    RewriteEngine On
    RewriteMap karlauth "prg:/usr/local/sbin/karl-ttyd-auth"

    # Terminal ttyd, même origine, GATED par le cookie de session karl.
    <Location "/ttyd/">
        # fail-closed : pas de cookie karl valide → 403, avant tout proxy
        RewriteEngine On
        RewriteCond "${karlauth:%{HTTP:Cookie}}" "!=OK"
        RewriteRule ".*" "-" [F]
        ProxyPass        "http://127.0.0.1:7681/" retry=0
        ProxyPassReverse "http://127.0.0.1:7681/"
    </Location>
    <Location "/ttyd/ws">
        RewriteEngine On
        RewriteCond "${karlauth:%{HTTP:Cookie}}" "!=OK"
        RewriteRule ".*" "-" [F]
        ProxyPass        "ws://127.0.0.1:7681/ws" retry=0
        ProxyPassReverse "ws://127.0.0.1:7681/ws"
    </Location>

L'expo cockpit existante (`ProxyPass / → 127.0.0.1:9876`) reste inchangée ; les
blocs `/ttyd*` doivent être déclarés **avant** le `/` fourre-tout.

⚠ **Ordre rewrite/proxy à valider en recette** : selon la version d'Apache,
l'ordre d'évaluation `RewriteRule [F]` vs `ProxyPass` peut différer. Le critère
de validation ci-dessous (curl sans cookie → **403**) DOIT être vérifié en
live ; si le proxy court-circuite le `[F]`, basculer le gate sur `RewriteRule
… [P]` (proxy piloté par rewrite) au lieu de `ProxyPass`.

## 5. Recette (mmi, après `apachectl configtest && systemctl reload apache2`)

1. **Sans cookie → refusé** (critère sécurité) :
   `curl -sI https://karl.iprospective.fr/ttyd/ | head -1` → **403**.
2. **Avec cookie valide → terminal** : se logguer sur le cockpit (pose le
   cookie), ouvrir une session → le terminal xterm.js s'attache
   (`wss://karl.iprospective.fr/ttyd/ws`).
3. **Non-régression cockpit** : `/` répond toujours (→ `:9876`).
4. **Pas de secret loggué** : la query de `/ttyd` n'est pas journalisée (le
   cookie est en en-tête, pas en query — rien à masquer côté logs d'accès).

## Réversibilité

Retirer les 2 blocs `<Location "/ttyd*">` + la `RewriteMap`, `reload apache2`,
et retirer le 2e `-R` du tunnel. Le validateur peut rester en place (inerte).
Aucune donnée mutée.
