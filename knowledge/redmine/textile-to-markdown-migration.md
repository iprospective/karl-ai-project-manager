---
type: knowledge
product: redmine
topic: migration
created: 2026-05-14
validated_on:
  - tasks.iprospective.fr (Redmine 6.1.1, MySQL 8, Ubuntu 22.04)
---

# Migration Textile → Markdown (CommonMark) sur Redmine

## Sens et contexte

Redmine stocke le texte au **format brut** (Textile ou Markdown) en BDD, et le rend
au format défini par `Setting.text_formatting`. Bascule = setter ce paramètre +
**convertir tout le contenu existant**, sinon l'ancien Textile sera mal rendu.

**Sens** : Textile → Markdown CommonMark (`common_mark`).

**Aucune rake task officielle** dans le core Redmine ne fait la conversion. La méthode
canonique repose sur un **script communautaire** (originellement Planio, patché ici) qui
appelle `pandoc -f textile -t gfm+smart` avec pre/postprocessing pour préserver les
spécificités Redmine.

**Risque** : ré-écriture massive de champs texte en BDD. Backup obligatoire.

## Pré-requis

| Item | Vérification |
|---|---|
| **Redmine ≥ 4.1** | Support CommonMark côté setting. Idéalement ≥ 5.x ou 6.x. |
| **`pandoc` installé** sur le serveur Redmine | `which pandoc` — sinon `apt install pandoc` ou snap |
| **Accès root au serveur** | pour stop service, dump BDD, cp script |
| **Backup BDD testable** | restauration validée — sans ça, pas de filet |
| **Fenêtre de maintenance** | typiquement 15-30 min de downtime |
| **Connaître `SECRET_KEY_BASE`** prod (Rails 8) | sinon le rake échouera au boot |

## Procédure générale (5 phases)

### Phase 1 — Recon

Analyser le contenu existant pour calibrer le risque :

```sql
-- Volumes
SELECT
  (SELECT COUNT(*) FROM issues WHERE description != '') AS issues,
  (SELECT COUNT(*) FROM journals WHERE notes != '') AS journals,
  (SELECT COUNT(*) FROM wiki_contents) AS wiki_pages,
  (SELECT COUNT(*) FROM wiki_content_versions) AS wiki_versions;

-- Patterns à risque
SELECT
  (SELECT COUNT(*) FROM wiki_contents WHERE text LIKE '%{{%}}%') AS wiki_macros,
  (SELECT COUNT(*) FROM wiki_contents WHERE text REGEXP '(^|\n)\\|') AS wiki_tables,
  (SELECT COUNT(*) FROM wiki_contents WHERE text LIKE '%<pre>%') AS wiki_pre;

-- Custom fields texte (le script de base ne les couvre pas)
SELECT id, name, field_format FROM custom_fields WHERE field_format IN ('text','long_text');

-- Top contenus par taille
SELECT 'journal' AS src, id, LENGTH(notes) FROM journals ORDER BY LENGTH(notes) DESC LIMIT 5;
SELECT 'issue' AS src, id, LENGTH(description) FROM issues ORDER BY LENGTH(description) DESC LIMIT 5;
SELECT 'wiki' AS src, page_id, LENGTH(text) FROM wiki_contents ORDER BY LENGTH(text) DESC LIMIT 5;
```

**Patterns particulièrement à risque** :
- `{{macro}}` du core Redmine ou de plugins (peuvent être abîmés)
- Tables Textile complexes
- Listes numérotées contenant `<pre>` (limitation connue)
- `<pre>` avec backslashes ou caractères spéciaux

Si une catégorie de contenu est très utilisée et atypique : prévoir un échantillonnage
visuel post-conversion.

### Phase 2 — Staging (test isolé)

**Toujours faire tourner la conversion sur un staging avant prod**, pour valider le rendu.

```bash
# 1. Dump prod
mysqldump -u <db_user> -p<db_pass> --single-transaction --routines --triggers \
  <db_name> > /tmp/<db>-snapshot.sql

# 2. Créer DB staging + grants (root MySQL)
mysql -e "CREATE DATABASE <db_name>_staging CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "GRANT ALL ON <db_name>_staging.* TO '<db_user>'@'localhost'; FLUSH PRIVILEGES;"

# 3. Import
mysql -u <db_user> -p<db_pass> <db_name>_staging < /tmp/<db>-snapshot.sql

# 4. Cloner l'install code
cp -a /home/<rmuser>/redmine /home/<rmuser>/redmine-staging
chown -R <rmuser>:<rmuser> /home/<rmuser>/redmine-staging

# 5. Adapter config/database.yml staging — pointer sur <db>_staging
sed -i 's/^  database: <db_name>$/  database: <db_name>_staging/' \
  /home/<rmuser>/redmine-staging/config/database.yml

# 6. Isoler log/ et tmp/ (si symlinks relatifs vers ../log et ../tmp)
mkdir -p /home/<rmuser>/log-staging /home/<rmuser>/tmp-staging/{pids,cache,sessions}
ln -sfn ../log-staging /home/<rmuser>/redmine-staging/log
ln -sfn ../tmp-staging /home/<rmuser>/redmine-staging/tmp

# 7. Désactiver l'envoi de mail en staging (config/configuration.yml :: production:)
#   production:
#     email_delivery:
#       delivery_method: :test

# 8. Générer un SECRET_KEY_BASE distinct pour staging
openssl rand -hex 64 > /tmp/staging-secret.txt
chmod 600 /tmp/staging-secret.txt && chown <rmuser>:<rmuser> /tmp/staging-secret.txt

# 9. Démarrer staging sur un port libre
sudo -u <rmuser> bash -c 'cd /home/<rmuser>/redmine-staging && \
  eval "$(rbenv init - bash)" && \
  SECRET_KEY_BASE=$(cat /tmp/staging-secret.txt) \
  nohup bundle exec rails server -u puma -e production -p 3002 \
  > /tmp/puma-staging.log 2>&1 & disown'

# 10. Probe
curl -sI -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:3002/
# attendu : 302 (redirection vers /login)
```

Si tu veux y accéder depuis ta machine : `ssh -L 3002:127.0.0.1:3002 <serveur>`.

### Phase 3 — Conversion staging

Installer le script (cf. fichier joint [scripts/convert_textile_to_markdown.rake](./scripts/convert_textile_to_markdown.rake)) :

```bash
# Copier le script
cp /path/to/knowledge/redmine/scripts/convert_textile_to_markdown.rake \
   /home/<rmuser>/redmine-staging/lib/tasks/
chown <rmuser>:<rmuser> /home/<rmuser>/redmine-staging/lib/tasks/convert_textile_to_markdown.rake

# Lancer (durée: ~1 sec / 5-10 modèles ; pour 7000 modèles, ~5-10 min)
sudo -u <rmuser> bash -c 'cd /home/<rmuser>/redmine-staging && \
  eval "$(rbenv init - bash)" && \
  SECRET_KEY_BASE=$(cat /tmp/staging-secret.txt) RAILS_ENV=production \
  bundle exec rake convert_textile_to_markdown' 2>&1 | tee /tmp/conv-staging.log

# Vérifier la liste des échecs pandoc (cosmétiques uniquement si le script est bien patché)
cat /tmp/pandoc-failures.log
```

Le script affiche un `.` par modèle traité et un `X` par échec pandoc (skip-on-failure
implémenté). À la fin : `Done converting N models. Pandoc failures: X`.

### Phase 4 — Switch staging + vérif visuelle

```bash
# Switch setting
mysql -u <db_user> -p<db_pass> <db_name>_staging \
  -e "UPDATE settings SET value='common_mark' WHERE name='text_formatting';"

# Restart puma staging (kill + relancer la commande de la phase 2 étape 9)
PID=$(ss -tlnp | awk '/:3002 / {match($0, /pid=[0-9]+/); print substr($0, RSTART+4, RLENGTH-4); exit}')
kill -TERM $PID; sleep 3
# … relancer …
```

**Vérifs à faire visuellement sur http://localhost:3002** (parcourir en parallèle de prod) :
- Tickets riches en formatting (listes, code, citations)
- Pages wiki avec liens internes `[[Page]]`
- Tableaux (si présents)
- Macros (si utilisées)
- Onglet "History" d'une page wiki → cliquer sur les anciennes versions

Si quelque chose est cassé : reporter dans le repo le diff prod vs staging, patcher
le script, wipe staging + reimport + relancer.

### Phase 5 — Prod

Une fois staging validé :

```bash
# 1. Récupérer SECRET_KEY_BASE prod AVANT de tuer le process
PID_PROD=$(ss -tlnp | awk '/:3000 / {match($0, /pid=[0-9]+/); print substr($0, RSTART+4, RLENGTH-4); exit}')
sudo cat /proc/$PID_PROD/environ | tr '\0' '\n' | grep SECRET_KEY_BASE > /tmp/prod-secret.env
chmod 600 /tmp/prod-secret.env && chown <rmuser>:<rmuser> /tmp/prod-secret.env

# 2. Backup BDD frais (NON NÉGOCIABLE)
mysqldump -u <db_user> -p<db_pass> --single-transaction --routines --triggers \
  <db_name> > /home/<rmuser>/<db>-pre-md-$(date +%F-%H%M).sql

# 3. Stop puma prod
kill -TERM $PID_PROD ; sleep 5
kill -0 $PID_PROD 2>/dev/null && kill -KILL $PID_PROD

# 4. Copier le script patché (depuis staging ou knowledge base)
cp /home/<rmuser>/redmine-staging/lib/tasks/convert_textile_to_markdown.rake \
   /home/<rmuser>/redmine-git/lib/tasks/
chown <rmuser>:<rmuser> /home/<rmuser>/redmine-git/lib/tasks/convert_textile_to_markdown.rake

# 5. Lancer la conversion
sudo -u <rmuser> bash -c 'cd /home/<rmuser>/redmine-git && \
  eval "$(rbenv init - bash)" && \
  set -a; source /tmp/prod-secret.env; set +a; \
  RAILS_ENV=production bundle exec rake convert_textile_to_markdown' \
  2>&1 | tee /tmp/conv-prod.log

# 6. Switch setting
mysql -u <db_user> -p<db_pass> <db_name> \
  -e "UPDATE settings SET value='common_mark' WHERE name='text_formatting';"

# 7. Restart puma prod (commande habituelle, ex: start.sh)
sudo -u <rmuser> /home/<rmuser>/start.sh

# 8. Vérifs rapides
curl -sI https://redmine.example.com/
# + login + ouverture de quelques tickets/pages
```

## Plan de rollback

À tout moment, en cas de problème majeur :

```bash
# Stop puma prod
kill -TERM $(ss -tlnp | awk '/:3000 /{match($0,/pid=[0-9]+/); print substr($0,RSTART+4,RLENGTH-4); exit}')

# Restore BDD
mysql -u <db_user> -p<db_pass> <db_name> < /home/<rmuser>/<db>-pre-md-YYYY-MM-DD-HHMM.sql

# Le setting text_formatting=textile est restauré automatiquement avec le dump

# Restart puma
sudo -u <rmuser> /home/<rmuser>/start.sh
```

Perte = les minutes entre le backup et le restore. C'est pourquoi on fait pendant
une fenêtre de maintenance creuse.

## Cleanup post-migration (après quelques jours stables)

```bash
# Drop staging DB
mysql -e "DROP DATABASE <db_name>_staging;"

# Supprimer install staging
rm -rf /home/<rmuser>/redmine-staging /home/<rmuser>/log-staging /home/<rmuser>/tmp-staging

# Supprimer le script de migration de prod (optionnel)
rm /home/<rmuser>/redmine-git/lib/tasks/convert_textile_to_markdown.rake

# Garder les backups quelques semaines minimum
```

## Modèles couverts par le script

| Modèle | Attribut | Note |
|---|---|---|
| `Setting` | `welcome_text` | Texte d'accueil |
| `Comment` | `content` | (souvent vide en pratique) |
| `WikiContent` | `text` | Version courante des pages wiki |
| `WikiContentVersion` | `text` (via getter, gère gzip) | Historique des pages wiki — **important** |
| `Issue` | `description` | Descriptions de tickets |
| `Message` | `content` | Forum posts |
| `News` | `description` | News projet |
| `Document` | `description` | Documents projet |
| `Project` | `description` | Description des projets |
| `Journal` | `notes` | Notes/commentaires sur les tickets |

**Non couvert** par le script :
- `CustomValue.value` (custom fields texte) — à ajouter si volume significatif détecté en recon
- `JournalDetail.value` (historique des changements de champs texte) — généralement marginal

## Différences avec le script Planio original

| Modif | Raison |
|---|---|
| `Comment[:content]` au lieu de `[:comments]` | La colonne s'appelle `content` en BDD (bug du script Planio) |
| Skip si `textile.empty?` | Pandoc plante sur input vide → faux échec |
| `WikiContentVersion` ajouté | Historique wiki sinon resté en textile, cassé après bascule |
| Un-escape `\_` dans `[[...]]` | Pandoc échappe `_` partout → wiki links cassés |
| Try/catch pandoc avec log dans `/tmp/pandoc-failures.log` | Continuer sur erreur isolée au lieu de tout planter |

## Validations en production

Notez ici les exécutions réelles :

- **2026-05-14** — `tasks.iprospective.fr` (Redmine 6.1.1) — 6974 modèles convertis, 0 échec.
  Volume : 1012 issues + 2049 journals + 28 wiki + 165 versions wiki + 8 projects.
  Durée : ~7 min de conversion + 2 min stop/start = ~10 min de downtime.

(à compléter pour chaque nouvelle migration)
