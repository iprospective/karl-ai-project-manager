---
name: mmi-env-sync
description: Synchronise un environnement de DEV/TEST local depuis la PROD (fichiers + base de données) via le framework de synchro du repo PM (tools/synchro/). Propose ou crée la conf d'environnement quand le projet utilise un framework connu (PrestaShop, Dolibarr, WordPress), sinon aide à écrire un script de synchro ad hoc en suivant le même pattern dump→import→adaptation. Usage : "/mmi-env-sync", ou langage naturel "récupère les données de prod dans ma base dev", "rafraîchis la base dev de <projet>", "synchronise l'environnement de test".
allowed-tools: Bash, Read, Write, Edit
---

# Skill : mmi-env-sync

Rapatrier la PROD vers un environnement **local** de dev/test (base + éventuellement fichiers), puis appliquer les **adaptations de sécurité** pour que l'instance locale ne touche jamais le monde réel ni la prod.

## Quand le déclencher

- « récupère / rafraîchis les données de prod dans ma base dev », « mets à jour la base de test », « synchronise l'environnement », « j'ai besoin des données prod en local »
- `/mmi-env-sync`
- Avant de tester/déboguer un comportement qui dépend de données réelles à jour.

## Le framework de synchro

Le framework vit dans le **repo PM**, sous **`tools/synchro/`** (versionné et distribué
avec `ai-project-management` — sur cette workstation : `/home/workspaces/ai/project-management/tools/synchro/`).
**Aucun secret en clair** : auth MySQL admin locale via `~/.my.cnf`, secrets distants/prod
via **Vaultwarden** (`resolve_secret "vaultwarden://…"`, URI dans la conf). Le dossier
`environments/` est **gitignoré** (confs machine-spécifiques, sans mot de passe).

```
sync.sh                      # point d'entrée
  ./sync.sh <env>            # charge environments/<env>.conf
  ./sync.sh <env> --db       # BDD seulement (cas le plus courant)
  ./sync.sh <env> --files    # fichiers seulement
  ./sync.sh <env> --yes      # non interactif
  ./sync.sh /chemin/x.conf   # conf explicite hors du dossier
environments/<env>.conf      # 1 fichier par environnement (variables)
lib/common.sh                # infra partagée (WORKSPACE_ROOT, MYSQL_HOST, …)
lib/helpers.sh               # log/confirm/guard_local_target/resolve_secret/auth MySQL
lib/db.sh                    # dump prod + import local (générique)
lib/<type>.sh                # spécifique au type : presta / dolibarr / wordpress
```

**Où l'exécuter : sur l'HOST** (`MathouDell`), pas dans le conteneur. C'est l'host qui a
les alias SSH de prod (avec ProxyJump) et un `~/.my.cnf` (root) qui atteint le MySQL du
conteneur dev (`10.0.3.11`). Le symlink `/home/workspaces → /zfs/workspaces` existe aussi sur l'host.

Pipeline de `sync.sh` : `guard_local_target` → (`<type>_sync_files`) → `db_dump_from_prod`
→ `db_import` (DROP/CREATE + import) → `<type>_adapt_db`.

## Cas 1 — framework connu : proposer/créer une conf

Types implémentés : **presta**, **dolibarr** (`lib/<type>.sh`). Pour un nouvel
environnement, copier une conf voisine et adapter. Variables clés :

| Variable | Rôle |
|---|---|
| `WEBSITE_TYPE` | `presta` / `dolibarr` / … → charge `lib/<type>.sh` |
| `SSH_AUTH` | alias SSH de la prod (= nom conteneur OVH, ou alias `~/.ssh/config`) |
| `DB_FROM` / `DB_TO` | base prod → base locale |
| `DB_PREFIX` | préfixe tables (`ps_`, `llx_`, …) |
| `DB_DUMP_STRATEGY` | `remote-backup-script` (prod a `backup/mysqlbackup_all.sh`) ou `remote-mysqldump` |
| `MYSQL_SANDBOX_ERROR` | `1` si le dump commence par `/*M!999999\- enable the sandbox mode */` (sinon import KO) |
| `WEBSITE_PATH` | racine projet locale sous `/home/workspaces` |
| `REMOTE_FILES_PATH` | chemin fichiers côté prod (presta: `public_html` ; doli: `public_html/documents`) |
| `DOMAIN` / `EMAIL` | domaine local + adresse vers laquelle rediriger les mails |

**Garde-fou** : `guard_local_target` refuse un `DB_TO` qui n'a pas un suffixe local
(`_test|_dev|_presta|_sync|_preprod|_local|_dolibarr`). Étendre la liste dans
`lib/helpers.sh` si un projet a un autre nom de base locale.

### Découvrir les valeurs prod proprement

```bash
ssh <SSH_AUTH> -- 'grep -hE "db_name|db_prefix" $(find ~ -maxdepth 4 -path "*conf/conf.php"|head -1)'  # doli
ssh <SSH_AUTH> -- 'ls backup/mysqlbackup_all.sh && zcat backup/mysql/<DB_FROM>.sql.gz | head -1'        # stratégie + sandbox
```

## Cas 2 — adaptations de sécurité (le point critique)

Après import, `<type>_adapt_db` doit **neutraliser tout ce qui, depuis le dev, pourrait
atteindre la prod ou le monde réel**. Ne jamais se contenter de l'import brut. Checklist
(à chercher dans la config — `ps_configuration` pour Presta, `llx_const` pour Dolibarr) :

- **Mails** : rediriger tous les envois vers `EMAIL` (Dolibarr: `MAIN_MAIL_FORCE_SENDTO` ;
  Presta: `PS_SHOP_EMAIL`/`PS_MAIL_USER`), forcer un envoi local, **vider les creds SMTP
  externes** (Brevo/Sendinblue) et couper tout **collecteur IMAP** (pointe sur la boîte prod).
- **Paiements** : tout PSP en **mode test/sandbox** (Dolibarr ex.: `MBIETRANSACTIONS_TEST=1`,
  `PAYPAL_API_SANDBOX=1`). Repérer les modules custom (`MMIPAYMENTS`, etc.).
- **Synchro / webhooks** : couper le master-switch (Dolibarr: `MMIPRESTASYNC_SYNC=0`) et
  **repointer les URLs vers le local** (sinon le dev pousse vers la prod !).
- **Domaine / SSL** : URLs locales, SSL off (surtout Presta : `PS_SHOP_DOMAIN`, `shop_url`).
- **Penser large** : balayer `value REGEXP 'https?://|<domaine prod>|brevo'`, lister
  `llx_cronjob`/jobs actifs, `llx_oauth_token`, api_keys. Ce que l'utilisateur oublie est
  souvent là.

**Secrets** : ne jamais écrire une clé en clair dans `environments/*.conf` (repo versionné).
Soit on **désactive** la fonctionnalité (le plus sûr), soit on résout au runtime via
`resolve_secret "vaultwarden://…"` (cf. `lib/helpers.sh`).

## Cas 3 — framework inconnu : script ad hoc

Pas de `lib/<type>.sh` adapté → écrire un script qui suit le **même pattern** :

1. dump prod (via `backup/mysqlbackup_all.sh` distant + rsync, ou `mysqldump` SSH) ;
2. `DROP/CREATE` la base locale + import (gérer la ligne sandbox si présente) ;
3. **adaptations de sécurité** (cf. Cas 2) — la partie qui demande de comprendre l'appli ;
4. fichiers : ne **jamais** écraser le code versionné ; ne rapatrier que les données
   (uploads/documents/médias).

Le placer dans `<projet>/scripts/` (convention historique `<projet>-<type>-sync.sh`) ou
créer un `lib/<type>.sh` si le type a vocation à se réutiliser.

## Exemple de référence : calicote Dolibarr

`environments/calicote-dolibarr-dev.conf` + `lib/dolibarr.sh`. Prod `erp_calicote`
(ssh `calicote-erp`) → local `calicote_dolibarr`. Lancer un rafraîchissement BDD :

```bash
cd /home/workspaces/ai/project-management/tools/synchro && ./sync.sh calicote-dolibarr-dev --db --yes
```
