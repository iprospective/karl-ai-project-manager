---
template: migration-wordpress
schema_version: "1.0.0"
applicable_to: "WordPress site → infra iprospective (conteneur LXC, Apache + PHP-FPM)"
created: 2026-05-16
---

# Plan de migration WordPress — `{{domain}}`

Playbook réutilisable pour migrer un site WordPress depuis un hébergeur externe
vers l'infra iprospective (conteneur LXC `{{target_container}}`, stack
Apache + PHP-FPM avec pool dédié `{{fpm_pool}}` — convention `<projet>-<phpver>`).

> Remplacer toutes les occurrences de `{{...}}` avant d'utiliser ce plan
> en projet. Garder ce fichier intact dans `templates/migrations/` pour les
> migrations suivantes.

## Variables à instancier

| Placeholder | Valeur | Notes |
|---|---|---|
| `{{client_slug}}` |  | ex: `lydiemariller` |
| `{{project_slug}}` |  | ex: `lydiemariller-com` |
| `{{domain}}` |  | ex: `lydiemariller.com` |
| `{{target_container}}` |  | ex: `prd` (LXC sur host iprospective) |
| `{{target_host_ssh}}` |  | ex: `prd.lxc` ou alias SSH |
| `{{fpm_pool}}` |  | ex: `lydiemariller-82` (projet-phpver) |
| `{{php_version}}` |  | 7.4 / 8.0 / 8.1 / 8.2 / 8.3 — **doit matcher la version source** |
| `{{app_path}}` |  | ex: `/var/www/{{client_slug}}/htdocs` |
| `{{db_name}}` |  | ex: `lydiemariller_wp` |
| `{{db_user}}` |  | ex: `lydiemariller` |
| `{{old_host}}` |  | nom de l'hébergeur source (ovh, o2switch, hostinger…) |
| `{{old_host_ssh}}` |  | accès SSH ou SFTP source |
| `{{old_doc_root}}` |  | racine WP côté source (ex: `~/public_html`) |
| `{{old_db_host}}`, `{{old_db_name}}`, `{{old_db_user}}` |  | DB source |
| `{{dns_registrar}}` |  | où sont les NS / records (gandi, ovh, cloudflare…) |
| `{{has_mail_on_domain}}` |  | oui/non — si oui, NE PAS toucher aux MX |

---

## Phase 0 — Reconnaissance & inventaire

**Objectif** : tout savoir avant de toucher quoi que ce soit. Pas de migration les yeux fermés.

### Source (hébergeur actuel)
- [ ] Credentials récupérés : SSH/SFTP, panel admin (cPanel/Plesk/managed), DB admin (phpMyAdmin / accès direct)
- [ ] Stockage des credentials dans Vaultwarden (collection client `{{client_slug}}`)
- [ ] Version WordPress : `wp core version` ou `wp-includes/version.php` → `$wp_version`
- [ ] Version PHP côté source : `php -v` (ou panel) — `{{php_version}}` doit matcher
- [ ] Version MySQL/MariaDB : `mysql --version`
- [ ] Volumétrie files : `du -sh {{old_doc_root}}` → noter la taille
- [ ] Volumétrie DB : `mysqldump ... | wc -c` ou check via panel
- [ ] Liste plugins (actifs + désactivés) : `wp plugin list` ou via `/wp-admin/plugins.php`
- [ ] Thème actif + thèmes secondaires
- [ ] WP-Cron : actif/désactivé, jobs planifiés (`wp cron event list`)
- [ ] Custom code hors plugins : `wp-content/mu-plugins/`, `wp-content/themes/<theme>/functions.php`
- [ ] WooCommerce / e-commerce ? — change le niveau de criticité (commandes en cours, paiements, stocks)
- [ ] Multisite ? — change la procédure (subdomain vs subfolder, network admin)

### DNS & email
- [ ] Registrar du domaine : `{{dns_registrar}}` — accès confirmé
- [ ] TTL actuel des records A/AAAA : `dig +short A {{domain}} && dig +short {{domain}} | head -1 | awk ...` (ou panel)
- [ ] Records actuels : A, AAAA, CNAME (www), MX, TXT (SPF/DKIM/DMARC)
- [ ] `{{has_mail_on_domain}}` : si **oui**, identifier le provider mail (Google Workspace, OVH mail, etc.) → **les MX/SPF/DKIM/DMARC NE DOIVENT PAS bouger**
- [ ] Sous-domaines existants (`webmail`, `mail`, `cpanel`, etc.) — à conserver ou non

### Volumétrie & trafic
- [ ] Trafic moyen (RPS, visiteurs/jour) — info Google Analytics ou logs
- [ ] Site critique (e-commerce, formulaires de prise de rdv) ou statique ?
- [ ] Fenêtre de maintenance acceptable : 5 min ? 1 h ? 1 nuit ?

### Backup défensif (avant tout)
- [ ] Backup files complet côté source : `tar czf /tmp/{{client_slug}}-files-$(date +%F).tar.gz -C {{old_doc_root}} .`
- [ ] Dump DB côté source : `mysqldump -h {{old_db_host}} -u {{old_db_user}} -p {{old_db_name}} --single-transaction --routines --triggers --quick > /tmp/{{client_slug}}-db-$(date +%F).sql`
- [ ] Rapatrier les 2 archives sur la workstation (`scp` ou via panel)
- [ ] **Vérifier** que le tar et le dump sont intègres (`tar tzf`, `head` sur le dump)

---

## Phase 1 — Préparation de l'infra cible (`{{target_container}}`)

**Objectif** : monter l'environnement vide, prêt à accueillir le site.

### Webserver + FPM
- [ ] SSH dans le conteneur : `ssh mathieu@{{target_host_ssh}}`
- [ ] Vérifier que PHP `{{php_version}}` est installé : `php{{php_version}} -v`
- [ ] Créer pool FPM dédié `/etc/php/{{php_version}}/fpm/pool.d/{{fpm_pool}}.conf` (copier un pool existant comme template, ajuster `[{{fpm_pool}}]`, `user/group`, `listen`, `chdir`, `php_admin_value[error_log]`, `slowlog`)
- [ ] Logs FPM : `/var/log/php/{{fpm_pool}}.error.log` + `/var/log/php/{{fpm_pool}}.slow.log` (mkdir + touch + chown)
- [ ] Reload FPM : `systemctl reload php{{php_version}}-fpm` (vérifier `systemctl status`)
- [ ] Vhost Apache `/etc/apache2/sites-available/{{domain}}.conf` :
  - DocumentRoot `{{app_path}}`
  - `<FilesMatch \.php$> SetHandler "proxy:unix:/run/php/{{fpm_pool}}.sock|fcgi://localhost"`
  - `AllowOverride All` (WordPress utilise `.htaccess` pour les permaliens)
  - VirtualHost :80 (HTTP) → on ajoute :443 après émission du cert
- [ ] `a2ensite {{domain}} && systemctl reload apache2`

### Base de données
- [ ] Créer DB + user :
  ```sql
  CREATE DATABASE {{db_name}} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER '{{db_user}}'@'localhost' IDENTIFIED BY '<password-from-vaultwarden>';
  GRANT ALL PRIVILEGES ON {{db_name}}.* TO '{{db_user}}'@'localhost';
  FLUSH PRIVILEGES;
  ```
- [ ] Password généré + stocké dans Vaultwarden (item `{{client_slug}} — DB MySQL prd`)

### Filesystem
- [ ] `mkdir -p {{app_path}} && chown -R www-data:www-data {{app_path}}`
- [ ] Vérifier `open_basedir` du pool FPM si activé : doit inclure `{{app_path}}`

### SMTP
- [ ] Vérifier qu'un relais SMTP local fonctionne (`msmtp` ou `postfix`) — sinon WordPress n'enverra pas les emails (récupération mdp, notifications)
- [ ] Si besoin, installer plugin `WP Mail SMTP` côté WordPress après import

---

## Phase 2 — Sync initial (site source toujours live)

**Objectif** : faire tourner un site complet côté cible, avant tout bascule DNS. Site source pas touché.

### Files
- [ ] rsync depuis source vers cible (en mode `--dry-run` d'abord pour estimer) :
  ```bash
  ssh mathieu@{{target_host_ssh}} \
    "rsync -avz --partial --progress \
       -e 'ssh -i ~/.ssh/id_ed25519' \
       {{old_host_ssh}}:{{old_doc_root}}/ {{app_path}}/"
  ```
  Variante si pas de SSH source : `wget` / `lftp mirror` / archive `tar.gz` rapatriée puis untaré côté cible.
- [ ] `chown -R www-data:www-data {{app_path}}`
- [ ] `find {{app_path}} -type d -exec chmod 755 {} \;` et `find {{app_path}} -type f -exec chmod 644 {} \;`
- [ ] `wp-config.php` accessible en 640 (contient mdp DB)

### Database
- [ ] Si pas déjà fait en Phase 0, dumper la DB source maintenant :
  `mysqldump -h {{old_db_host}} -u {{old_db_user}} -p {{old_db_name}} --single-transaction --routines --triggers --quick --default-character-set=utf8mb4 > /tmp/{{client_slug}}-db-init.sql`
- [ ] Transférer le dump sur la cible : `scp /tmp/{{client_slug}}-db-init.sql mathieu@{{target_host_ssh}}:/tmp/`
- [ ] Importer : `mysql -u {{db_user}} -p {{db_name}} < /tmp/{{client_slug}}-db-init.sql`
- [ ] Vérifier les tables : `mysql -u {{db_user}} -p {{db_name}} -e "SHOW TABLES;"` (doit contenir `wp_options`, `wp_posts`, etc.)

### wp-config.php
- [ ] Ajuster `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` aux valeurs cibles
- [ ] Vérifier `$table_prefix` (souvent `wp_`, mais peut être custom)
- [ ] Ajouter (si pas présent) :
  ```php
  define('WP_DEBUG', false);
  define('WP_DEBUG_LOG', false);
  define('DISALLOW_FILE_EDIT', true);
  define('AUTOMATIC_UPDATER_DISABLED', false);
  ```
- [ ] **Salts** : peut conserver les mêmes (sinon tous les utilisateurs sont déconnectés au cutover, ce qui n'est pas forcément un mal — choix à faire)

### Pas de search-replace si le domaine reste identique
Si `{{domain}}` est le même côté source et cible, **aucune réécriture d'URL** nécessaire dans la DB.
Si le domaine change ou si HTTP → HTTPS forcé, prévoir :
```bash
cd {{app_path}} && wp search-replace 'http://{{old_domain}}' 'https://{{domain}}' \
  --all-tables --skip-columns=guid --report-changed-only
```

---

## Phase 3 — Tests sur cible (DNS pas encore basculé)

**Objectif** : valider que le site répond correctement avant de toucher au DNS.

- [ ] Override `/etc/hosts` côté workstation :
  ```
  <IP-publique-{{target_container}}>  {{domain}}  www.{{domain}}
  ```
- [ ] Tester homepage : `curl -I -H 'Host: {{domain}}' http://<ip-cible>/` → 200 OK attendu
- [ ] Dans navigateur (avec `/etc/hosts` actif) : naviguer, tester login admin, formulaires, médias, recherche, pages internes
- [ ] **Permaliens** : si les URLs `/?p=123` marchent mais pas `/article-titre/`, c'est un problème de rewrite — vérifier `.htaccess` + `AllowOverride All` dans vhost
- [ ] Vérifier logs en parallèle :
  - `ssh mathieu@{{target_host_ssh}} 'tail -F /var/log/php/{{fpm_pool}}.error.log'`
  - `ssh mathieu@{{target_host_ssh}} 'tail -F /var/log/apache2/{{domain}}-error.log'`
- [ ] Si erreurs : fixer, re-tester. Ne pas avancer tant que phase 3 n'est pas verte.
- [ ] HTTPS test : si on a un cert temporaire (snake-oil ou DNS-01), tester en HTTPS. Sinon, accepter de tester en HTTP pour l'instant — HTTPS viendra après bascule DNS via HTTP-01.

---

## Phase 4 — Préparation cutover

**Objectif** : préparer le terrain pour minimiser le downtime.

- [ ] Réduire TTL DNS à **300s** (5 min) **24 à 48h avant** la bascule. Faire côté `{{dns_registrar}}` sur les records A/AAAA de `{{domain}}` et `www.{{domain}}`.
- [ ] Préparer page de maintenance simple à activer côté **source** (plugin WP "Maintenance Mode" ou `.htaccess` qui sert un HTML statique) → bloquer les écritures pendant le delta final.
- [ ] Préparer le script de bascule (commandes prêtes à coller, pas tapées à la main pendant le stress) :
  - rsync delta avec `--delete`
  - dump + scp + import DB
  - DNS update
- [ ] Plan de rollback explicite (cf. section dédiée plus bas)
- [ ] Annoncer la fenêtre de migration au client + tester qu'on a son contact direct (téléphone) pendant l'opération

---

## Phase 5 — Cutover (J-day)

**Objectif** : basculer en minimisant le downtime. Ordre critique.

1. [ ] **T-0** : Activer maintenance mode côté source (`{{old_host_ssh}}` → plugin WP ou `.htaccess`)
2. [ ] **T+1min** : Final rsync delta files :
   ```bash
   ssh mathieu@{{target_host_ssh}} \
     "rsync -avz --delete --partial --progress \
       -e 'ssh -i ~/.ssh/id_ed25519' \
       {{old_host_ssh}}:{{old_doc_root}}/ {{app_path}}/"
   ```
   Attention au `--delete` : il supprime côté cible les fichiers absents côté source. Vérifier qu'aucun fichier custom n'a été ajouté côté cible entre-temps.
3. [ ] **T+5min** : Final mysqldump + import :
   ```bash
   # source
   mysqldump -h {{old_db_host}} -u {{old_db_user}} -p {{old_db_name}} \
     --single-transaction --routines --triggers --quick \
     --default-character-set=utf8mb4 > /tmp/{{client_slug}}-db-final.sql
   # transfer
   scp /tmp/{{client_slug}}-db-final.sql mathieu@{{target_host_ssh}}:/tmp/
   # target — DROP + recreate pour partir propre
   ssh mathieu@{{target_host_ssh}} \
     'mysql -u root -p -e "DROP DATABASE {{db_name}}; CREATE DATABASE {{db_name}} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" \
        && mysql -u root -p -e "GRANT ALL ON {{db_name}}.* TO '\''{{db_user}}'\''@'\''localhost'\'';" \
        && mysql -u {{db_user}} -p {{db_name}} < /tmp/{{client_slug}}-db-final.sql'
   ```
4. [ ] **T+10min** : Mettre à jour le DNS chez `{{dns_registrar}}` — records A (et AAAA si IPv6) de `{{domain}}` et `www.{{domain}}` → IP `{{target_container}}`
5. [ ] **T+12min** : Attendre propagation (TTL 300s → quasi-instantané). Vérifier depuis plusieurs points :
   ```bash
   dig +short A {{domain}} @1.1.1.1
   dig +short A {{domain}} @8.8.8.8
   dig +short A {{domain}} @ns1.{{dns_registrar}}
   ```
6. [ ] **T+15min** : Émettre cert Let's Encrypt avec HTTP-01 :
   ```bash
   ssh mathieu@{{target_host_ssh}} 'certbot --apache -d {{domain}} -d www.{{domain}} --non-interactive --agree-tos -m mathieu@iprospective.fr'
   ```
7. [ ] **T+18min** : Désactiver maintenance mode côté source ET côté cible (s'il y en avait un). Forcer HTTPS si pas déjà :
   ```apache
   # dans vhost :80
   RewriteEngine On
   RewriteCond %{HTTPS} off
   RewriteRule (.*) https://%{HTTP_HOST}%{REQUEST_URI} [R=301,L]
   ```
8. [ ] **T+20min** : Tests fumée sur la nouvelle infra (homepage, admin, contact form, page internal). Surveillance logs FPM/apache en // pendant 30 min minimum.

---

## Phase 6 — Post-cutover (J+0 à J+7)

**Objectif** : stabiliser, sécuriser, documenter.

- [ ] Surveillance 24h : `tail -F /var/log/php/{{fpm_pool}}.error.log /var/log/apache2/{{domain}}-*.log`
- [ ] Vérifier emails sortants : envoyer un test depuis WP (mot de passe oublié, etc.)
- [ ] Vérifier formulaires de contact (form to email, arrivée côté client)
- [ ] Cache : purger complètement W3 Total Cache / WP Rocket / autres si présents
- [ ] **Setup backups** :
  - Cron mysqldump quotidien → `/var/backups/{{client_slug}}/db/`
  - Cron rsync files → destination de backup (autre host / borg / restic)
  - Tester la restauration (au moins une fois !)
- [ ] **Monitoring** : ajouter `{{domain}}` à l'outil d'uptime (uptimerobot / monit / etc.)
- [ ] **Documenter** dans `clients/{{client_slug}}/projects/{{project_slug}}/project/environments.md` :
  - `host: {{target_host_ssh}}`
  - `app_path: {{app_path}}`
  - `fpm_pool: {{fpm_pool}}`
  - `logs: { app: ..., fpm: /var/log/php/{{fpm_pool}}.error.log }`
  - `secrets_source: vaultwarden/collection-{{client_slug}}`
- [ ] Mettre à jour `project/overview.md` : statut → "migré le YYYY-MM-DD"
- [ ] Auto-updates WordPress : configurer (`wp-config.php` ou plugin) — au minimum les mises à jour mineures

---

## Phase 7 — Cleanup (J+14)

**Objectif** : refermer la migration une fois la stabilité confirmée.

- [ ] Attendre 14 jours minimum de stabilité avant de tuer l'ancien hébergement
- [ ] Annoncer la résiliation à `{{old_host}}` (lettre/email selon T&Cs)
- [ ] Récupérer un dernier dump complet (files + DB) en cold storage (sait-on jamais)
- [ ] Nettoyer DNS : enlever les sous-domaines obsolètes pointant vers l'ancien host
- [ ] Si emails étaient hébergés chez `{{old_host}}` : migration emails séparée (hors scope ce playbook), NE PAS résilier tant que pas fait
- [ ] Fermer le ticket Redmine de migration avec récap dates + volumétrie finale + incidents éventuels
- [ ] Mettre à jour `BASELINE.md` si audit prévu derrière

---

## Rollback (au cas où la migration tourne mal)

Le rollback est **trivial tant que le DNS n'a pas été basculé** : il n'y a rien à faire, l'ancien host répond toujours.

Si DNS déjà basculé et problème majeur côté nouvelle infra :
1. [ ] Restaurer maintenance mode côté nouvelle infra
2. [ ] Remettre le DNS sur l'ancienne IP
3. [ ] TTL réduit (300s) → propagation rapide
4. [ ] Désactiver maintenance côté source
5. [ ] Investiguer le problème côté cible sans pression (le site répond depuis l'ancien host)
6. [ ] Si des écritures ont été faites côté nouvelle infra entre cutover et rollback :
       - dumper la DB cible
       - identifier les diff côté ancien
       - merge manuel ou accepter la perte
       - **C'est pour ça qu'on garde la fenêtre de cutover courte et qu'on prévient le client.**

---

## Checklist credentials à récolter en Phase 0

| Item | Format | Où le stocker |
|---|---|---|
| SSH/SFTP source | host + user + key/pwd | Vaultwarden / `secrets/{{client_slug}}/source-ssh` |
| Panel hébergeur source | URL + login + 2FA recovery | Vaultwarden |
| DB source | host + db + user + pwd | Vaultwarden |
| WordPress admin | URL admin + login | Vaultwarden |
| Registrar DNS | URL + login + 2FA | Vaultwarden |
| Email provider (si applicable) | URL + login | Vaultwarden |
| Cert Let's Encrypt cible | (auto via certbot) | rien à stocker |
| DB cible | db + user + pwd généré | Vaultwarden (item séparé "DB cible") |

---

## Notes pour le prestataire (toi)

- **Phase 0 est la plus longue et la plus chiante**. Tu auras envie de la sauter. Ne la saute pas. C'est elle qui évite les surprises.
- **Garde l'ancien hébergement payé 1-2 mois après la bascule.** Le coût est dérisoire vs la sérénité d'avoir un rollback.
- **Communique sur la fenêtre de maintenance** au client 48h avant minimum, et envoie un mail "tout est OK" après bascule.
- **Si WooCommerce / paiements** : prévenir des heures plus creuses, prévoir un script qui fige `wp_options.siteurl` + désactive plugins de paiement pendant la fenêtre.
- **Multisite WP** : ce playbook ne couvre pas le multisite — règles différentes sur `wp-config.php`, `.htaccess`, et les replaces de domaine sont plus complexes.
