# env-runtime — runtime des envs de workspace (RM1834 / RM1947)

Substrat **générique** qui rend un env de workspace *servi* : vhost Apache par env,
logs PHP séparés par worktree (pool FPM **partagé** au workspace, cf. `tools/php-fpm/`),
BDD partagée + clone à la demande. La config **applicative** (creds, base-URL —
briques C4/C5 de RM1947) relève des provisionneurs framework (`tools/env-provisioners/`,
à venir) et n'est pas couverte ici.

## Pièces

| Pièce | Rôle | Où elle tourne |
|---|---|---|
| `pm-env-helper.sh` | helper **privilégié** fail-closed (vhost/BDD/logs/squelette) — brique F1 RM1947 | box de dev (root, via sudo) |
| `scripts/pm-env-session.py` | orchestre worktree + `.user.ini` + appels helper — RM1834 | host (user) |
| `scripts/pm-env-expose.py` | expose un env porté par un **daemon HTTP** (reverse proxy `vhost-proxy-add`) — RM2358 | box de dev (user) |

## Convention hostname (RM2358)

Tout env de test est joignable en `http://<project>-rm<id>[-s<seq>].lxc/` :

- env **PHP** (DocumentRoot) : vhost posé par `pm-env-session` (verbe `vhost-add`) ;
- env porté par un **daemon HTTP** en loopback (karl-agent, serveur non-PHP) :
  `pm-env-expose.py expose <rmid> --port <p>` crée le vhost reverse proxy
  (verbe `vhost-proxy-add`), enregistre l'allocation (`var/env-expose.json` du
  workspace), synchronise `test_url` + CF 14 « Environnement de test », et
  journalise dans le `.log.md` du ticket. `unexpose` défait tout. Le hostname
  est **dérivé du dossier d'env**, jamais saisi (suffixe `-s<seq>` conservé
  pour les worktrees de session).

  Le proxy est émis sur **HTTP (:80) ET HTTPS (:443)** — les navigateurs
  accèdent souvent aux `.lxc` en https (d'autres vhosts de l'instance ont du
  SSL) ; sans le `:443`, la requête tombait sur le vhost SSL par défaut
  (« Apache2 Ubuntu Default Page »). Le `:443` réutilise le certificat snakeoil
  auto-signé (dev local → avertissement de certificat attendu, comme les autres
  `.lxc`) ; override possible via `PM_ENV_SSL_CERT` / `PM_ENV_SSL_KEY`. Si le
  cert est absent, le helper se rabat sur `:80` seul avec un avertissement
  (fail-safe : jamais de configtest KO).

Recette validée par le pilote manuel RM1834 du 2026-07-02 (matnat/site_sf7) :
vhost `<repo>-rm<id>.lxc` + `.user.ini` `error_log` par worktree (surchargeable car
`php_value[]` dans `common.conf.inc`, RM2081) + pool FPM partagé.

## Déploiement du helper (box de dev)

**Canal normal (RM2358)** : `sudo mmi-pm core update` installe/rafraîchit le
helper automatiquement (copie idempotente `tools/env-runtime/pm-env-helper.sh`
→ `/usr/local/sbin/pm-env-helper`, root:root 755) — même canal root que le
code du core, barrière mot de passe sudoers. NB : `core update` s'exécutant
depuis l'ancien `bin/mmi-pm`, une évolution du bloc d'install lui-même ne prend
effet qu'au run suivant.

**Bootstrap d'une box neuve** (avant le premier `core update`) :

```bash
scp tools/env-runtime/pm-env-helper.sh root@dev.lxc:/usr/local/sbin/pm-env-helper
ssh root@dev.lxc 'chown root:root /usr/local/sbin/pm-env-helper && chmod 755 /usr/local/sbin/pm-env-helper'
```

Sudoers (`/etc/sudoers.d/pm-env-helper`, valider avec `visudo -c`) — **inchangé** : le
motif `pm-env-helper *` couvre déjà les verbes ajoutés depuis (dont `ws-init`/`ws-perms`) :

```
# RM1947 F1 — l'user de dev pilote le runtime des envs via le helper fail-closed
mathieu ALL=(root) NOPASSWD: /usr/local/sbin/pm-env-helper *
```

Toute la sécurité repose sur le helper (whitelist de verbes, validation stricte,
marqueur « managed-by » sur les vhosts, drop limité aux BDD `*_rm<id>`, configtest
Apache avant reload, audit syslog `pm-env-helper`).

## Façade CLI `mmi-pm env vhost` (RM2372)

Les verbes vhost du helper sont exposés par la **CLI unique** `mmi-pm`, plutôt
qu'en `sudo pm-env-helper` brut :

```bash
mmi-pm env vhost proxy-add <name> <port>     # reverse proxy <name>.lxc → 127.0.0.1:<port>
mmi-pm env vhost add <name> <docroot> <sock> # vhost PHP
mmi-pm env vhost remove <name>               # retrait
mmi-pm env vhost proxy-add … --dry-run       # prévisualise sans muter
```

`mmi-pm env vhost` est une **façade mince** : le privilège reste **confiné au
helper** (règle sudoers NOPASSWD dédiée), mmi-pm route via `sudo -n <helper>`
**sans re-exec mot de passe** et **sans nouvelle règle sudoers**. La seule op
« mot de passe » de mmi-pm demeure `core update`. Automation préservée :
`pm-env-session` (host-side, ssh+sudo -n) et `pm-env-expose` passent par cette
voie NOPASSWD. `pm-env-expose.py` appelle `mmi-pm env vhost` en interne (front
door unique).

## Squelette de workspace : `ws-init` / `ws-perms` (RM2909)

Le modèle de perms multi-user (RM2438 / T6 RM2502) verrouille la racine d'un workspace en
`2750 pm:pm` : group `r-x`, **pas d'écriture**. C'est un invariant voulu — on ne veut pas
qu'un dev ou son agent puisse renommer ou supprimer `repos/`, `envs/`, `.mmi-pm/`. Mais il
a un corollaire longtemps non outillé : **personne d'autre que root ne peut créer ces
dossiers**. `pm-project-new` et `pm-env-init` écrivent sous l'identité de l'appelant et
échouaient donc en `Permission denied` au milieu de la création d'un projet, qu'il fallait
encadrer à la main :

```bash
sudo chmod 2770 <workspace>            # ouvrir avant     ← ce qu'on ne fait plus
pm-project-new.py … / pm-env-init.py
sudo pm-perms.py --apply <workspace>   # refermer après   ← ni ça
```

Deux verbes remplacent ce runbook :

```bash
mmi-pm env vhost …                                    # (rappel : façade des verbes vhost)
sudo -n /usr/local/sbin/pm-env-helper ws-init  <workspace>   # crée le squelette
sudo -n /usr/local/sbin/pm-env-helper ws-perms <workspace>   # (ré)applique le modèle
```

`ws-init` crée, si absents : le dossier client, la racine du workspace, tous les dossiers
du modèle (`.mmi-pm/` et ses sous-dossiers, `repos/`, `envs/`, `tmp/ sessions/ logs/
data/`) et le `.gitignore` de whitelist du repo `-core` — puis applique le modèle de
perms. Idempotent : sur un workspace déjà complet, il ne fait rien.

**Le modèle n'est pas dans le helper.** La liste des dossiers vient de
`pm-perms.py --list-dirs`, les modes et owners de `pm-perms.py --apply`, le texte du
`.gitignore` de `pm-env-init.py --print-gitignore`. Le layout peut bouger sans qu'une
ligne de shell privilégié change. Corollaire de déploiement : le helper appelle le core
**déployé** (`/zfs/workspaces/.mmi-pm-core`) — les deux partent par le même
`sudo mmi-pm core update`, et un core en retard fait échouer `ws-init` avec un message qui
le dit.

**Appel automatique.** `pm-project-new` et `pm-env-init` passent par `ws-init` **quand et
seulement quand** c'est nécessaire (pièce de squelette manquante *et* racine non
inscriptible), et repassent `ws-perms` en fin de course. Sur un workspace historique
`mathieu:mathieu` — encore la majorité — les deux sont des no-op silencieux : rien ne
change, et surtout aucune migration vers `pm:pm` ne se déclenche au détour d'un
`pm-env-init`. Une migration se décide.

**Garde-fous** (mêmes exigences fail-closed que les autres verbes) :

- chemin résolu par `realpath`, sous `/zfs/workspaces`, profondeur **exacte**
  `<client>/<projet>`, deux composants conformes au slug de `pm-project-new` ;
- **aucun composant symlink** : `chmod`/`chown` déréférencent — un `.mmi-pm` symlinké vers
  le core PROD root-owned se ferait sinon `chown pm` ;
- **pas d'adoption silencieuse** : une racine qui existe déjà n'est reprise que si elle
  appartient à `pm` (déjà au modèle) ou à l'invocateur (le `chown` ne lui donne alors rien
  qu'il n'ait déjà — même doctrine que `daemon-add`). root, un autre dev, un compte de
  service : refus ;
- les scripts du core exécutés **en root** sont vérifiés root-owned et non modifiables
  hors root avant exécution — sans quoi un membre du groupe `pm` obtiendrait root en
  éditant un fichier ;
- audit syslog (`logger -t pm-env-helper`) sur chaque mutation.

Tests sans privilège : `bash tools/env-runtime/test-ws-init.sh` (extrait les gardes du
fichier de production — rien n'est recopié) et `python3 scripts/test_pm_perms.py`.

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
