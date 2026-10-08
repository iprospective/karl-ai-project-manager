# tools/synchro — clone d'un site de production vers un environnement de recette

`sync.sh` copie les **fichiers** et la **base** d'un site de production vers un
environnement local de test, puis applique les adaptations qui l'empêchent de se prendre
pour la production (domaine, mails, indexation, services tiers).

```bash
./sync.sh <env>                 # conf environments/<env>.conf (non versionnée)
./sync.sh /chemin/recette.conf  # conf explicite, typiquement dans le dépôt du site
./sync.sh <conf> --files | --db # une moitié seulement
./sync.sh <conf> --yes          # sans confirmation
```

Il s'exécute **sur la machine cible** (celle qui sert la recette) : il lit la production
par SSH (`SSH_AUTH`) et n'y écrit jamais. Sur un conteneur de recette distant, on y copie
le framework puis on le lance avec l'agent SSH transféré :

```bash
rsync -a --delete tools/synchro/ <hôte>:/root/pm-synchro/
ssh -A <hôte> 'TEST_DOMAIN=<domaine de recette> /root/pm-synchro/sync.sh <conf> --yes'
```

Le domaine de recette vient du `pm.env` de l'instance (`TEST_DOMAIN`, `TEST_HOST`,
`DEV_DOMAIN` — RM3221) ; hors de l'instance, on le passe par l'environnement.

## Types de site (`WEBSITE_TYPE`)

| Type | Module | Adaptations |
|---|---|---|
| `presta` | `lib/presta.sh` | maintenance, SSL, mails, domaine, services cloud neutralisés (RM2932) |
| `dolibarr` | `lib/dolibarr.sh` | — |
| `wordpress` | `lib/wordpress.sh` | URL et chemin disque remplacés (wp-cli, données sérialisées comprises), `blog_public=0`, mails coupés et `X-Robots-Tag: noindex` par un mu-plugin de recette, extensions listées désactivées, `wp-config.php` et compte MySQL propres à la recette (RM3250) |

Conf WordPress minimale :

```bash
WEBSITE_TYPE=wordpress
WORKSPACE_ROOT=/home/siteadm/<compte>/public   # surcharge celui de common.sh
WEBSITE_PATH=<site>-test
MYSQL_HOST=localhost
SSH_AUTH=root@<prod>
REMOTE_FILES_PATH=/chemin/du/site/en/prod
PROD_URL=https://www.<site>.fr
DOMAIN="<site>.${TEST_DOMAIN}"
DB_FROM=<base_prod>
DB_TO=<site>_test                               # suffixe _test exigé par le garde-fou
DB_DUMP_STRATEGY=remote-mysqldump-socket        # aucun mot de passe de prod à détenir
EMAIL=<adresse de dev>
WP_CLI="sudo -u php_<compte> php8.4 /usr/local/bin/wp"
FILES_OWNER=php_<compte>:<groupe>
WP_DEACTIVATE_PLUGINS="crowdsec"                # extensions qui parlent à la prod
WP_RECETTE_MU="/chemin/sans-traceur.php"        # mu-plugins propres au site
```

Le dossier de la recette, son vhost et son pool PHP sont un préalable : `sync.sh` ne les
crée pas.

Tests : `scripts/test_synchro_domaine_test.py`, `scripts/test_synchro_wordpress.py`.
