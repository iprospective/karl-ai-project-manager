# env-runtime — runtime des envs de workspace (RM1834 / RM1947)

Substrat **générique** qui rend un env de workspace *servi* : vhost Apache par env,
logs PHP séparés par worktree (pool FPM **partagé** au workspace, cf. `tools/php-fpm/`),
BDD partagée + clone à la demande. La config **applicative** (creds, base-URL —
briques C4/C5 de RM1947) relève des provisionneurs framework (`tools/env-provisioners/`,
à venir) et n'est pas couverte ici.

## Pièces

| Pièce | Rôle | Où elle tourne |
|---|---|---|
| `pm-env-helper.sh` | helper **privilégié** fail-closed (vhost/BDD/logs) — brique F1 RM1947 | box de dev (root, via sudo) |
| `scripts/pm-env-session.py` | orchestre worktree + `.user.ini` + appels helper — RM1834 | host (user) |

Recette validée par le pilote manuel RM1834 du 2026-07-02 (matnat/site_sf7) :
vhost `<repo>-rm<id>.lxc` + `.user.ini` `error_log` par worktree (surchargeable car
`php_value[]` dans `common.conf.inc`, RM2081) + pool FPM partagé.

## Déploiement du helper (box de dev)

```bash
scp tools/env-runtime/pm-env-helper.sh root@dev.lxc:/usr/local/sbin/pm-env-helper
ssh root@dev.lxc 'chown root:root /usr/local/sbin/pm-env-helper && chmod 755 /usr/local/sbin/pm-env-helper'
```

Sudoers (`/etc/sudoers.d/pm-env-helper`, valider avec `visudo -c`) :

```
# RM1947 F1 — l'user de dev pilote le runtime des envs via le helper fail-closed
mathieu ALL=(root) NOPASSWD: /usr/local/sbin/pm-env-helper *
```

Toute la sécurité repose sur le helper (whitelist de verbes, validation stricte,
marqueur « managed-by » sur les vhosts, drop limité aux BDD `*_rm<id>`, configtest
Apache avant reload, audit syslog `pm-env-helper`).

## Config côté PM

`pm.config.yml :: env_runtime` (ssh_host, helper, log_dir, workspace_map) ;
runtime par repo dans `.mmi-pm/meta.yml › repos[] › runtime: {pool, docroot, db,
db_clone_default}` (absent = env « code seul »).

## Clone BDD : toujours optionnel

La BDD reste **partagée par défaut**. Le clone dédié `<db>_rm<id>` se décide
par ticket : `--db-clone` / `--no-db-clone` tranchent sans question ; sinon la
**question est posée** (session interactive), pré-remplie par le **défaut
projet** `runtime.db_clone_default` (false si absent) ; hors TTY (hook, agent)
le défaut projet s'applique silencieusement. Au teardown, seul le clone est
droppé — jamais la BDD partagée.

### Paramètres du clone (`runtime.db_clone`)

```yaml
db_clone:
  exclude_tables: ['%_log', '_histo%']   # motifs LIKE : données exclues,
                                         # structure toujours copiée (logs, cache…)
  post_sql:                              # fixups appliqués SUR LE CLONE après copie
    - "UPDATE config SET value = 'http://{host}/' WHERE name = 'site_url'"
    - "UPDATE config SET value = 'dev-{rmid}@example.invalid' WHERE name = 'email_from'"
```

Placeholders `post_sql` : `{db}` (source), `{clone}`, `{rmid}`, `{host}`
(`<repo>-rm<id>.lxc`). Sécurité : le SQL du manifeste est exécuté par le helper
via un compte MySQL **confiné au clone** (`pm_env_exec`, aucun droit global,
credentials root-only sur la box) — il ne peut ni lire ni écrire hors du clone,
et jamais la BDD partagée. Un post-SQL en échec laisse le clone en l'état
(corriger le manifeste, ou `db-drop` puis recréer).

## Usage

```bash
pm-env-session.py create 2099                 # worktree + branche + vhost + .user.ini
pm-env-session.py create 2099 --db-clone      # + clone BDD dédié <db>_rm2099
pm-env-session.py teardown 2099               # vhost + logs + clone BDD + worktree
                                              # (branche et BDD partagée CONSERVÉES)
pm-env-session.py list
```

## Hooks D1/D2 (automatique)

`pm-task-status-update` déclenche l'env de session sur les transitions de
statut (RM1834) : **`en_cours` → create**, **`ferme` → teardown**. Best-effort,
jamais bloquant (un teardown refusé — worktree sale — laisse le ticket se
fermer et l'env se gère à la main). Conditions : tâche co-localisée, manifeste
`repos:` **mono-repo**, bare présent. Opt-out global :
`pm.config.yml :: env_runtime.auto_session: false`.
