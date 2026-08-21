> 📂 **Module `environments-reference` — quand lire ceci :** j'écris ou j'édite un aspect `environments.md` · je cherche le nom exact d'un champ d'environnement · je déclare un `post_deploy` ou un chemin de logs.
> **Outils :** `templates/aspects/common/environments.md` · **Préchargé par :** *(personne — ouvert à la demande)*.

# Environnements — format de l'aspect (référence)

Détaché de `environments.md` par RM2755 : ces sections décrivent la **forme** du
fichier d'aspect — noms d'env admis, champs, conventions de chemins. On les ouvre
quand on ÉCRIT un `environments.md`, pas à chaque tâche. Les **règles d'usage**
(quelle commande de connexion, cascade, `target_env`, secrets) restent dans
`environments.md`, préchargé.

### Noms et champs

**Énumération des noms d'env standard :**
`local | dev | test | staging | prod | demo | qa | sandbox | <nom-custom-kebab-case>`

> **`staging` et `preprod` sont un seul et même environnement** (fusionnés en v1.36.0) :
> l'env de non-régression avant prod, déployé depuis **`preprod_branch`** quand le projet
> est en **flux 3 branches** (opt-in, RM2030), **sinon** depuis `integration_branch`
> (modèle 2 branches). **Valeur
> canonique = `staging`** ; `preprod` reste accepté comme **alias** (le statut Redmine
> id 20 s'appelle toujours « MEP/Tester en preprod » et le narratif MEP ci-dessous parle
> de « preprod » — c'est le même env que `staging`). Ne pas déclarer deux entrées
> distinctes pour ce rôle.

Custom autorisé si le projet a une particularité (ex: `staging-eu`, `staging-archive`,
`prod-canary`).

**Champs par environnement :**
- `name` (obligatoire, enum ci-dessus)
- `status` : `active | disabled | planned`
- `url`, `admin_url` : URLs publiques/admin
- `ssh_alias` : **alias SSH** `~/.ssh/config` (avec `ProxyJump`/`HostName`/`User`/clés
  préconfigurés), **à utiliser de préférence** pour toute connexion. Ex: `calicote-presta`.
- `ssh_target` : **cible SSH explicite** `user@hostname` (fallback quand aucun alias
  n'est défini). Ex: `calicote@srv1.sfy-gestion.com`.
- `host`, `user`, `app_path`, `branch` : identité machine, user système, chemin du code,
  branche déployée
- `fpm_pool`, `logs.app`, `logs.fpm`, `logs.access` : observabilité
- `secrets_source` : pointeur vers un secret d'un vault déclaré (cf. section « Gestion des secrets »)
- `post_deploy` : **liste de commandes shell** à exécuter après un déploiement sur cet
  env (ex. purge du cache applicatif). C'est la forme **scriptée** de la procédure de
  déploiement, à préférer à la prose (la prose ne sert qu'à expliquer le *pourquoi*).
  Deux règles **impératives** :
  - **Déclaratif, NON auto-exécuté** : ce champ *documente* les commandes ; aucun outil
    ne les lance automatiquement pour l'instant. Un humain les exécute délibérément. Sur
    la prod, toute commande modifiant l'état exige le **consentement explicite** (cf.
    « Règle de sécurité prod »).
  - **Chemins ABSOLUS obligatoires** : ancrer chaque chemin sur `app_path`. Un
    `rm -rf var/cache/*` *relatif* vise `/var/cache` (dossier système Linux) s'il est
    lancé du mauvais cwd — écrire `rm -rf /home/<user>/public_html/var/cache/*`.
- `notes` : libre

### Conventions de chemins

**Logs (`logs.app` / `logs.fpm` / `logs.access`)** : chemins des logs, préfixés de
l'host si le fichier est sur une machine distante (`<host>:<path>`).
- `logs.app` : log applicatif (Symfony/PrestaShop, ex: `var/logs/prod.log`).
- `logs.fpm` : log du pool PHP-FPM (cf. § conventions FPM, ex: `/var/log/php/calicote-74.error.log`).
- `logs.access` : access log du serveur web. **Convention prod iProspective (OVH)** :
  un fichier par vhost sur le serveur hébergeur, à
  `/var/log/nginx/<domaine>_access.log` (+ `<domaine>_error.log`).
  Ex: `sfy-srv1:/var/log/nginx/calicote.com_access.log`. Utile pour analyser la charge
  de crawl (bots/scrapers), diagnostiquer des pics, ou auditer les accès.

**Tableau `env_vars[]`** : liste des variables d'environnement attendues (noms,
description, dans quels envs elles existent). **Sans les valeurs** — celles-ci sont
soit dans le `.env` local (gitignored), soit dans un vault via `secrets_source`.
