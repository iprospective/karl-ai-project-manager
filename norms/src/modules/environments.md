> 📂 **Module `environments` — quand lire ceci :** je me connecte à / référence un environnement · je manipule un secret (vault, quel qu'il soit).
> **Outils :** `ssh_alias`, `resolve-secret.sh` · **Préchargé par :** worker-dev, worker-infra.

### Environnements (aspect `environments.md`)

Aspect dédié à la déclaration des environnements d'exécution d'un projet (dev, test,
staging, prod, etc.), distinct de `hosting.md` (provider/coûts/DNS).

**Format** : frontmatter avec liste `environments[]`, chaque entrée décrivant un env.
Voir `templates/aspects/common/environments.md`.

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

**Connexion SSH (règle d'usage)** : pour se connecter à un env, utiliser **`ssh_alias`
s'il est renseigné** (il porte les `ProxyJump`/clés de `~/.ssh/config` — cf. convention
OVH « alias = nom du conteneur »), **sinon `ssh_target`** (`user@hostname` explicite).
`host`/`user` restent indicatifs (préfixe des logs distants, contexte) et ne sont pas la
commande de connexion.

**Logs (`logs.app` / `logs.fpm` / `logs.access`)** : chemins des logs, préfixés de
l'host si le fichier est sur une machine distante (`<host>:<path>`).
- `logs.app` : log applicatif (Symfony/PrestaShop, ex: `var/logs/prod.log`).
- `logs.fpm` : log du pool PHP-FPM (cf. § conventions FPM, ex: `/var/log/php/calicote-74.error.log`).
- `logs.access` : access log du serveur web. **Convention prod iProspective (OVH)** :
  un fichier par vhost sur le serveur hébergeur, à
  `/var/log/nginx/<domaine>_access.log` (+ `<domaine>_error.log`).
  Ex: `sfy-srv1:/var/log/nginx/calicote.com_access.log`. Utile pour analyser la charge
  de crawl (bots/scrapers), diagnostiquer des pics, ou auditer les accès.

**Cascade** : un `environments.md` peut exister au niveau client (conventions par défaut
sur l'host, user, secrets_source) et au niveau projet (surcharge ou complète).

**Lien avec les tâches** : le frontmatter de tâche peut référencer un env via
`target_env: <name>`. Si présent, `test_url` se déduit de `environments.<target_env>.url`
(sauf si `test_url` est explicitement surchargé). Pour les **envs de session par
ticket** (RM1834), `pm-env-session` tient `test_url` à jour tout seul : `create`
écrit `http://<repo>-rm<id>.lxc/` (frontmatter + CF « Environnement de test »),
`teardown` les **vide** — ne jamais laisser une URL morte affichée (RM2229).

> **Résolution du worktree : PAR BRANCHE, jamais par chemin deviné (RM2394).**
> Le vhost et l'`env_name` restent l'**identité stable** du ticket
> (`<repo>-rm<id>.lxc`), mais le **worktree** est trouvé via sa branche `<id>-*`
> (`git worktree list`), quel que soit le nom du dossier : canonique
> `envs/<repo>-rm<id>` **ou** discriminé par session `envs/<repo>-dev-<id>-s<seq>`
> (RM2034), **ou** renommé/créé à la main. C'est la seule convention qui survit au
> multi-session et aux `git worktree move` — l'alternative (forcer un nom canonique
> à la création) casserait la discrimination RM2034. Conséquence : `pm-env-session
> create` et `pm-cockpit-test-env create` **réutilisent** le worktree déjà monté
> (pris avec `pm-branch-start --worktree`) et posent le vhost/runtime **par-dessus**
> (idempotent, le helper réécrit le `DocumentRoot`), au lieu d'échouer en `rc=128`.
> Résolveur partagé : `pm-env-session.worktree_for_branch()`.

**Tableau `env_vars[]`** : liste des variables d'environnement attendues (noms,
description, dans quels envs elles existent). **Sans les valeurs** — celles-ci sont
soit dans le `.env` local (gitignored), soit dans un vault via `secrets_source`.

### Gestion des secrets — vaults déclarés

Les credentials sensibles (mots de passe, tokens, clés) **ne sont jamais commités**,
ni dans le repo PM public, ni dans le repo projets privé. Ils vivent dans un
**gestionnaire de secrets** et sont **référencés** dans les documents PM par un URI.

**Plusieurs vaults peuvent coexister** (RM2662) : chacun est une **instance** déclarée
dans le registre providers (`pm.config.yml :: providers.servers`, axe `secret`), nommée
par un slug, avec un défaut et une surcharge possible **par client ou par projet**.

```yaml
providers:
  defaults:
    secret: vw-ipro                 # vault par défaut
  servers:
    vw-ipro:     { axis: secret, type: vaultwarden, url: "${VAULT_URL:-…}" }
    kdbx-perso:  { axis: secret, type: keepass, file: "~/vaults/ipro.kdbx" }
```

**Aucun secret dans cette déclaration** : URLs, types et chemins seulement. Les
identifiants d'accès sont **par développeur**, dans `~/.config/mmi-pm/.env`, nommés
par slug **normalisé** (majuscules, non-alphanum → `_`) :
`SECRET__VW_IPRO__CLIENTID`, `SECRET__KDBX_PERSO__FILE`, `…__TOKEN`.

**URI — trois formes, toutes valides :**
```
secret://<instance>/<chemin…>[#champ]      instance nommée explicitement
secret:<chemin…>[#champ]                   instance par défaut (cascade projet/client)
vaultwarden://<org>/<collection>/<item>    forme historique — supportée définitivement
```

Ex : `secret://vw-ipro/calicote-agents/prod-db`, ou
`vaultwarden://iprospective/calicote-agents/prod-db` (équivalent, jamais à réécrire).

**Backends disponibles** : `vaultwarden` (défaut iProspective), `keepass` (fichier
`.kdbx`, dépendance `python3-pykeepass`). D'autres s'ajoutent par le point d'extension
`pm_secrets.register_backend()` sans toucher aux appelants.

> **Secrets d'un client : la collection `<client>-agents` d'abord.** Déclarer une
> instance dédiée sert aux **intervenants** qui ont leur propre outil, ou à un client
> qui **impose** son gestionnaire. Pour les secrets d'un client hébergés chez nous, la
> voie normale reste une collection `-agents` du vault iProspective (ci-dessous).

**Architecture du vault par défaut** (chez iprospective) :

```
Organization iProspective
├── <client>            ← collections existantes, accès Mathieu uniquement
├── <client>-agents     ← sous-scope pour les items que les agents peuvent lire
│   └── membre : karl@iprospective.fr (User, Read-only)
└── iprospective-agents ← idem pour les secrets internes (Redmine bot, n8n, etc.)
    └── membre : karl@iprospective.fr (User, Read-only)
```

- Un seul user d'agents : `karl@iprospective.fr` (alias technique unique)
- Scope **read-only** sur les collections `*-agents` uniquement
- Les credentials critiques (root SSH, BDD admin, master gitlab, etc.) restent en
  dehors du scope agents

**Cycle de vie des sessions :**

| Action | Outil | Acteur |
|---|---|---|
| Déverrouillage | `scripts/unlock-vault.sh [-i <instance>]` (demande le secret humain — master password ou passphrase —, jamais stocké) ou, dans le **cockpit**, le bouton **🔓 déverrouiller** de l'en-tête, qui n'apparaît que si un coffre est fermé (RM2748) | toi (humain) |
| Résolution d'un secret | `scripts/resolve-secret.sh "<uri>" [champ]` | agent / script |
| Verrouillage manuel | `scripts/lock-vault.sh [<instance>]` | toi |
| Inventaire d'un vault | `scripts/vault-list.sh [-i <instance>] [filtre]` | toi / agent |
| Quel vault pour ce projet ? | `scripts/pm-providers.py resolve secret` | toi / agent |

Le déverrouillage démarre un daemon local `vault-agentd.py` qui :
- garde **une session par instance**, **en mémoire** uniquement (pas de fichier, pas
  même tmpfs) — déverrouiller le vault d'un client ne prolonge pas celui d'iProspective
- expose un socket Unix `/run/user/$UID/vault-agentd.sock` (chmod 600)
- verrouille **chaque instance** après inactivité (`VAULT_IDLE_TIMEOUT`, défaut 8h)
  et/ou à une heure fixe (`VAULT_LOCK_AT_HOUR`, défaut 23h), et ne s'arrête que
  lorsqu'il ne reste plus aucune instance ouverte

**Règles strictes :**
1. Un agent ne demande **jamais** le secret de déverrouillage (master password,
   passphrase) ; si `resolve-secret.sh` sort en code 2, l'agent dit à l'humain « lance
   `unlock-vault.sh`, ou déverrouille depuis le cockpit » et attend. Le mode non
   interactif (`--stdin`) existe pour un appelant qui **transmet** un secret déjà saisi
   par l'humain (le cockpit) — jamais pour qu'un agent en fabrique ou en réutilise un
2. Les secrets résolus **ne sont jamais loggués**, jamais écrits sur disque, jamais
   inclus dans un commit ou un transcript. Un diagnostic peut nommer les **clés**
   d'identifiants trouvées, jamais leurs valeurs
3. La rotation des identifiants d'agent est trimestrielle (ou immédiate en cas de doute)
4. Les agents 24/7 (cron nocturne, n8n) ne peuvent fonctionner que dans la fenêtre
   d'unlock manuel ou via un sous-scope dédié explicitement autorisé (cas particulier)
5. Un URI visant une **instance inconnue** est refusé, jamais rabattu sur le vault par
   défaut — chercher un secret dans le mauvais coffre est l'erreur silencieuse à éviter

**Identifiants** — par dev, dans `~/.config/mmi-pm/.env`, nommés par slug d'instance
(`SECRET__<SLUG>__…`). Les variables historiques `VAULT_URL` / `BW_CLIENTID` /
`BW_CLIENTSECRET` restent lues en repli tant qu'un dev n'a pas migré.

**Convention dans `environments.md` et autres aspects** : utiliser
`secrets_source: secret://<instance>/<chemin>` (ou la forme historique
`vaultwarden://…`, toujours valide) comme pointeur, jamais la valeur brute. Documenter
dans `client/security.md` (ou équivalent) la liste des items référencés et leur rôle,
pour audit humain.

