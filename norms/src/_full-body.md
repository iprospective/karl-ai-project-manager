
# Normes de gestion des tâches — v1.38.0

## Configuration des chemins (`pm.config.yml`)

Tous les chemins du système (racine du repo PM, racine du repo projets,
emplacement des entités, des projets, des tâches, des symlinks de liaison
code ↔ PM) sont **paramétrés** dans `pm.config.yml` à la racine du repo PM.

**Objectif** : pouvoir déplacer le repo PM, déplacer le repo projets, ou
réorganiser la structure interne **sans toucher au code des scripts ni à la
doc des agents**.

**Lib** : `scripts/pm_paths.py` expose `PMConfig.load()` qui charge la config,
résout `${VAR}` depuis `.env`, et fournit `.path(key, **kwargs)` pour résoudre
n'importe quel chemin via les patterns définis. Tous les scripts du repo
**doivent** passer par cette lib — jamais de concaténation manuelle ni de
hardcode `clients/`.

**Patterns standards** (clés de `paths:` dans `pm.config.yml`) :

| Clé | Résolution par défaut |
|---|---|
| `entities_dir` | `{projects_root}/clients` |
| `entity` | `{entities_dir}/{entity}` |
| `entity_client_dir` | `{entity}/client` |
| `entity_memory_dir` | `{entity}/memory` |
| `entity_projects_dir` | `{entity}/projects` |
| `entity_used_dir` | `{entity}/projects_used` |
| `project` | `{entity_projects_dir}/{project}` |
| `project_dir` | `{project}/project` |
| `project_memory_dir` | `{project}/memory` |
| `tasks_dir` | `{project}/tasks` |
| `task_file` | `{tasks_dir}/RM{id}_{slug}.md` |
| `task_log_file` | `{tasks_dir}/RM{id}_{slug}.log.md` |
| `workspace_link` | `{project}/workspace` |
| `reverse_link` | `{workspace_dir}/.mmi-pm` |

**Override local** : `pm.config.local.yml` (gitignored) peut surcharger
n'importe quelle clé pour un déploiement spécifique.

**Usage côté script** :
```python
from pm_paths import PMConfig
cfg = PMConfig.load()
cfg.projects_root                                      # Path
cfg.path("task_file", entity="lemathou", project="x", id=42, slug="foo")
for ent, proj, _ in cfg.iter_projects(entity=None): ...
cfg.find_task(rm_id)                                   # Path | None
cfg.find_project_by_redmine_id(rm_proj_id)             # (Path, Path) | (None, None)
```

**Usage côté doc / agents** : les chemins sont nommés par leur pattern
logique (ex: `paths.task_file` pour le fichier d'une tâche), non par leur
expansion filesystem. La résolution par défaut reste écrite ci-dessus pour
référence humaine.

## Outillage obligatoire en session PM — v1.35.0

En **session PM** (workspace PM-tracké via `.mmi-pm`, ou travail dans le repo PM), toute
opération touchant à l'**état des tâches, aux branches git, aux repos/submodules ou aux
tickets Redmine** passe par les **skills/scripts PM dédiés** — **jamais à la main**. C'est
ce qui garantit la cohérence Redmine ↔ MD ↔ worklog de session et l'application des
couplages NORMS (auto-assignation, notes, `status_history`, logs, filigrane IA, temps/tokens).

**Règle anti-trou** : si une opération de cette nature a un outil, l'utiliser ; si elle n'en
a pas, c'est un **trou d'outillage à combler** (créer le script/skill) — pas une exception à
faire à la main. En particulier, toute opération qui **amende l'état d'une tâche** est
branchée derrière `pm-task-status-update.py` (**source unique des transitions**), qui propage
Redmine + MD + log + worklog de session. Le worklog de session (`pm-session-status.py`) est
alimenté **automatiquement** par les scripts qui modifient l'état des tâches (via
`pm_session_hook.py`) ; cf. RM1875.

### Couverture actuelle (à compléter au fil des trous identifiés)

| Domaine | Opération | Outil canonique |
|---|---|---|
| Tâche | créer | `pm-task-add.py` · `mmi-pm-task-add` |
| Tâche | changer le statut | `pm-task-status-update.py` · `mmi-pm-task-status-update` |
| Tâche | commenter | `pm-task-comment.py` · `mmi-pm-task-comment` |
| Tâche | lier (relates/depends/blocks) | `pm-task-link.py` · `mmi-pm-task-link` |
| Tâche | description / checklist | `pm-task-description-update.py` |
| Tâche | estimation / métriques / temps-tokens | `pm-task-metrics-push.py`, `pm-task-tick.py` |
| Tâche | sync depuis Redmine | `pm-task-sync.py` · `mmi-pm-task-sync` |
| Tâche | lister / afficher | `pm-task-list.py`, `pm-task-show.py` |
| Projet / client | créer / bootstrap | `pm-project-new.py`, `pm-project-bootstrap.py`, `pm-client-new.py` |
| Ticket Redmine (bas niveau) | note / fetch / tag IA / config | `redmine-post-note.py`, `redmine-fetch-*.py`, `redmine-tag-ia.py`, `redmine-config-check.py` |
| Session | worklog d'avancement | `pm-session-status.py` · `mmi-pm-session-status` |
| **Branches / repos / submodules** | créer branche par ticket, commit+push conventionné, base de version | **⚠ trou — aucun outil dédié** (cf. § « Branche de travail par ticket », § « Commit + push systématique ») |

## Structure des dossiers

### Repo project-management (système, public)

```
project-management/                   # racine : pm.config.yml :: roots.pm_dir
  pm.config.yml                       # config de chemins (résolution centralisée)
  pm.config.local.yml                 # surcharge locale (gitignored, optionnel)
  norms/
    NORMS.md                          # version courante (ce fichier)
    CHANGELOG.md                      # historique des évolutions
    archive/                          # snapshots de toutes les versions
  templates/
    client.md                         # template client
    project.md                        # template projet
    task.md                           # template tâche (skeleton)
    RM9999_*.md                       # exemple complet pour CI
  agents/
    worker-common.md                  # règles communes des workers
    worker-{role}.md                  # rôles spécifiques
    orchestrateur.md
    reviewer.md
    summarizer.md                     # génération auto des Changelog/Pistes/Remarques
  scripts/
    pm_paths.py                       # lib de résolution de chemins (PMConfig)
    validate-task.py
    priority.py                       # ordonnancement par ROI
    pm-dashboard.py                   # CLI dashboard (statuts, ROI, en cours, activité)
    pm-project-bootstrap.py           # instancie les bootstrap-tasks dans un projet
    redmine-test.py                   # test de connexion API Redmine
    redmine-fetch-task.py             # fetch ticket Redmine → génère le MD
    redmine-fetch-updates.py          # récupère les nouveautés depuis le dernier check
    redmine-post-note.py              # poste une note (+ statut + assignation) sur un ticket
    invoke.md
    cron.example.sh
```

### Repo projets (privé, gitignored dans le repo PM)

Racine : `pm.config.yml :: roots.projects_root` (résolu depuis `$PROJECTS_PATH`).
Structure interne définie par les patterns de `paths:` — la représentation
ci-dessous montre la **résolution par défaut**.

```
{projects_root}/                      # = $PROJECTS_PATH (repo ai-projects)
  README.md
  {entities_dir}/                     # = projects_root/clients
    {entity}/                         # entité = client | product | self (slug)
      {entity_client_dir}/            # = entity/client  — cahier des charges
        overview.md                   # OBLIGATOIRE — frontmatter + sommaire
        hosting.md                    # aspect — optionnel
        contracts.md                  # aspect — optionnel
        ...                           # tout aspect pertinent
      {entity_memory_dir}/            # = entity/memory  — mémoire structurée (agents)
      Changelog.md                    # AUTO — activité agrégée
      Pistes.md                       # AUTO — idées non décidées
      Remarques.md                    # AUTO — observations factuelles
      {entity_projects_dir}/          # = entity/projects
        {project}/                    # = entity_projects_dir/{project-slug}
          {project_dir}/              # = project/project  — cahier des charges
            overview.md               # OBLIGATOIRE — frontmatter + sommaire
            hosting.md                # aspect — optionnel
            stack.md
            data-model.md
            workflows.md
            audience.md               # exemples — uniquement les aspects pertinents
            ...
          {project_memory_dir}/       # = project/memory  — mémoire spécifique projet
          Changelog.md                # AUTO
          Pistes.md                   # AUTO
          Remarques.md                # AUTO
          {tasks_dir}/                # = project/tasks
            RM{id}_{titre-kebab}.md         # = paths.task_file
            RM{id}_{titre-kebab}.log.md     # = paths.task_log_file
```

#### Commit + push systématique (obligatoire)

Toute modification d'un fichier rattaché à un projet PM **doit être suivie
d'un `git add <fichiers> && git commit && git push` immédiat**, dans le repo
git approprié. La règle s'applique à **deux périmètres** :

1. **Dossier projet PM côté `{projects_root}` (= ai-projects)** : `overview.md`,
   aspects, fichiers de tâche `RM*.md`/`.log.md`, ou structure d'entité
   (`client/`, `memory/`). Repo cible :
   `gitlab:iprospective/ai-artificial-intelligence/ai-projects.git`.

2. **Workspace de code lié au projet** côté `/zfs/workspaces/<...>/` — identifié
   par la **paire de symlinks** :
   - côté PM : `{paths.workspace_link}` (typiquement `…/projects/<slug>/workspace`)
     pointe vers le workspace
   - côté workspace : `{paths.reverse_link}` (`.mmi-pm`) pointe vers le projet PM

   Tout fichier modifié dans ce workspace (code, conf, docs internes) doit être
   commit+push dans le repo applicatif du workspace lui-même (remote GitLab
   canonique `git:`/`gitlab:iprospective/<...>`, **pas** ai-projects ; cf.
   « Remote canonique GitLab » ci-dessous).

**Règles communes aux deux périmètres** :
- Stager **uniquement** les fichiers touchés (jamais `git add .` ou `-A`),
  pour ne pas embarquer d'autres modifs en cours non liées qui ne sont pas
  de ta responsabilité — chacun est responsable de ses propres modifs.
  **Vérification active au commit (obligatoire) — v1.29.0, généralisée v1.30.1** :
  **tous les repos partagés** — `ai-projects` **comme le repo système
  `project-management`** (NORMS, `templates/`, `scripts/`, `pm.*.yml`) et **le
  workspace de code** — sont **fréquemment dirty en concurrence** (plusieurs
  sessions/agents en parallèle laissent des fichiers modifiés ou non suivis qui ne te
  concernent pas ; ex. typique : `pm.pricing.yml`, `pm-task-tick.py` modifiés par une
  autre tâche pendant que tu édites NORMS). La règle « ne committer que ses propres
  modifs » vaut donc **dans chaque repo, sans exception**. Avant tout
  commit : (1) stager par **chemin explicite** les seuls fichiers de la tâche
  courante (pas de glob large qui ratisse) ; (2) **relire le set stagé**
  (`git diff --cached --name-only`) et confirmer que **chaque** entrée concerne bien
  cette tâche ; (3) committer seulement alors. Ne **jamais** committer un fichier
  qu'on n'a pas soi-même modifié dans la session courante, même s'il apparaît dirty
  (ni un fichier non suivi appartenant à une autre tâche). Une solution d'isolation
  propre (workspaces instanciés par projet / zones de stash temporaires) est **à
  l'étude** — cf. ticket dédié
- Message de commit court, dans la langue du repo, précisant
  l'entité/projet/tâche concerné
- Push systématique : pas de "je commit, le user pushera" — le repo doit
  refléter l'état canonique à tout moment, sinon les autres agents (ou toi
  dans une session future) travaillent sur une vue divergente
- Si le push échoue (conflit avec `origin/<branche>`), `git pull --rebase`
  puis re-push ; en cas de conflit non trivial, escalader au demandeur
- Ne **jamais** committer un dossier projet PM dans le repo
  `project-management/` lui-même : `projects/` est gitignored par construction
  (cf. section précédente)
- Si le workspace de code n'est pas (encore) un repo git, c'est probablement
  une lacune de bootstrap — ouvrir/relancer la tâche `002-git-repos` du
  bootstrap plutôt que de "skipper" le commit

Cette règle s'applique à tous les agents (workers, summarizer, reviewer, et
agents pilotés interactivement par l'utilisateur via Claude Code).

#### Remote canonique GitLab, MR, et gotchas API — v1.20.4

- **GitLab est le remote canonique** : quand un repo de code a un remote GitLab
  (typiquement `origin`, alias SSH `git:` → `gitlab.iprospective.fr`), c'est lui
  qu'on utilise **par défaut** pour push, branches et MR. C'est aussi lui que
  traque la branche d'intégration locale.
- **Miroir gogs déprécié** : le miroir `gogs:` est **déprécié de manière
  générale**. Il reste actif **uniquement sur le projet `pisceen/prestashop`**.
  Partout ailleurs, ne plus pousser vers gogs (ni le maintenir en sync) — tout
  passe par GitLab.
- **Livraison par MR** (pas de merge direct sur la branche d'intégration) : créer
  une merge request de la branche de ticket vers la branche de base (version
  active ou `dev`, cf. sous-sections suivantes), puis la merger.
- **Gotcha glab/API GitLab — les `%2F` ne passent pas** : sur
  `gitlab.iprospective.fr`, le front Apache **rejette les chemins projet
  URL-encodés** (`iprospective%2Fdolibarr%2F…` → 404 Apache). Workaround
  systématique : utiliser l'**ID numérique** du projet, récupéré sans slash via
  une recherche :

  ```bash
  # 1) trouver l'ID numérique (pas de %2F dans une recherche)
  glab api --hostname gitlab.iprospective.fr "projects?search=<nom-repo>"
  # 2) agir avec l'ID (ex. créer une MR vers la branche de version active)
  glab api --hostname gitlab.iprospective.fr --method POST "projects/<id>/merge_requests" \
    -f source_branch="<RM-id>-<slug>" -f target_branch="19.0-mmi" -f title="…" \
    -f remove_source_branch=true
  # 3) merger
  glab api --hostname gitlab.iprospective.fr --method PUT "projects/<id>/merge_requests/<iid>/merge"
  ```
- **Tracer dans le ticket** : une fois la MR créée, renseigner le CF Redmine
  `GIT PR` (id 4) avec son URL (cf. sous-section suivante).

#### Branche de travail par ticket (obligatoire) — v1.17.0

Tout travail de code rattaché à un ticket PM se fait sur une **branche dédiée
au ticket**, jamais directement sur la branche d'intégration (`main`, `19.0-mmi`,
etc.). Convention de nommage **systématique** :

    <RM-id>-<slug-court>

où `<RM-id>` est l'identifiant Redmine (sans préfixe) et `<slug-court>` un
résumé court en kebab-case du sujet (≈ 2-4 mots, **pas** le titre complet de la
tâche). Exemple : `1762-etransactions-historique`.

- La branche est créée depuis la branche d'intégration courante du repo de code.
- Le frontmatter `git.branch` de la tâche pointe vers cette branche (cf. section
  « Lien Redmine ↔ MD ») ; `git.mr_url` vers la MR/PR une fois ouverte.
- **Renseigner le custom field Redmine « GIT Branche » dès la création de la
  branche** (v1.18.0) : le CF Redmine `GIT Branche` (id 3, format string) reçoit
  le **nom de la branche** ; le CF `GIT PR` (id 4) reçoit l'URL de la MR/PR une
  fois ouverte. C'est le CF dédié, **pas une note** : il rend l'info visible et
  filtrable côté Redmine. Le frontmatter MD `git.branch` / `git.mr_url` reste le
  miroir local.
- À la livraison, merge dans la branche d'intégration (via MR si le repo l'exige).
- (Multi-serveur V2) le schéma `agent/{server}/RM{id}-titre` reste l'exception
  réservée à l'orchestration distribuée ; en mono-machine, utiliser la forme
  courte ci-dessus.

#### Projets versionnés : branche de version active (base de branchement) — v1.20.0

Certains projets ne suivent pas un simple modèle `prod`/`dev` mais une **famille
de versions**, chacune avec sa propre branche d'intégration. C'est typiquement le
cas des projets et **modules Dolibarr** : en plus de `dev` (= prochaine version)
et `master`, il existe une **branche par version** (`14.0`, `15.0-mmi`,
`16.0-mmi`, `19.0-mmi`…), et l'une d'elles est la **version active** = celle
déployée en production.

Le modèle de versionnement est **déclaré dans le frontmatter de l'`overview.md`
du projet** via le bloc `versioning` (absent ⇒ projet non versionné, modèle
`prod`/`dev` classique) :

```yaml
versioning:
  scheme: dolibarr        # type de versionnement (ou null)
  active_version: "19.0"  # version déployée en production
  active_branch: 19.0-mmi # branche d'intégration de la version active (base des tickets prod)
  next_branch: dev        # branche de la prochaine version (base des tickets next-version)
```

- Pour un module appartenant à un écosystème (ici Dolibarr), `active_version` suit
  celle de l'application hôte.
- Le choix de la **branche de base** d'un ticket dépend de la cible :
  - ticket `feature`/`fix` **pour la prod actuelle** → partir de `active_branch`
    (ex. `19.0-mmi`) ;
  - ticket **réservé à la prochaine version active** → partir de `next_branch`
    (ex. `dev`).
- La branche de ticket `<RM-id>-<slug-court>` est tirée de cette branche de base
  et y est remergée à la livraison : la branche de base joue alors le rôle de
  « branche d'intégration » au sens de la sous-section précédente.
- En cas de doute sur la cible (prod actuelle vs prochaine version), **demander
  avant de brancher** : se tromper de base impose un rebase/cherry-pick ultérieur.

### Workspace projet — symlinks bidirectionnels `.mmi-pm` ↔ `workspace`

Chaque projet a **deux emplacements** distincts mais liés :

| Emplacement | Contenu | Repo git |
|---|---|---|
| `{workspace_dir}/` — variable selon projet, ex: `/zfs/workspaces/<P>/` ou `/zfs/workspaces/<entity>/<P>/` | Code source du projet | repo de code (ex: `iprospective/dev/<P>`) |
| `paths.project` (par défaut `{projects_root}/clients/<C>/projects/<P>/`) | Cahier des charges, tâches, mémoire | `ai-projects` |

Les deux emplacements se référencent **mutuellement** par symlinks (chemins
absolus, définis dans `pm.config.yml :: paths.reverse_link` et
`paths.workspace_link`) :

```
{workspace_dir}/.mmi-pm    → paths.project           # paths.reverse_link
paths.project/workspace    → {workspace_dir}         # paths.workspace_link
```

**Création (les deux symlinks ensemble) :**
```bash
# Côté workspace (code) :
ln -s "$(python3 -c 'from pm_paths import PMConfig; \
  print(PMConfig.load().path("project", entity="<C>", project="<P>"))')" \
  "$WORKSPACE_DIR/.mmi-pm"

# Côté PM (référence inverse) :
ln -s "$WORKSPACE_DIR" "$(python3 -c '…path("workspace_link", …)…')"
```

(Un futur `pm sync-links` automatisera ces deux opérations.)

**Bénéfices :**
- Un agent travaillant dans le workspace voit code ET tâches/docs (`.mmi-pm/project/`,
  `.mmi-pm/tasks/`)
- Un agent travaillant côté PM (dans `paths.project`) accède directement au code via
  `workspace/` — utile pour consulter une stack, un commit, un fichier en cours de
  modification
- Bidirectionnel : si le dossier d'un côté est déplacé, on a un point de repère côté
  opposé pour rétablir le lien sans chercher
- La centralisation est préservée (l'orchestrateur scanne `cfg.projects_root` directement,
  sans suivre `workspace/`)

**Conventions :**
- Le symlink `.mmi-pm` côté workspace est **caché** (préfixe `.`) pour ne pas polluer
  l'arborescence du code
- Le symlink `workspace` côté PM est **dans la racine du dossier projet PM** (au même
  niveau que `project/`, `tasks/`, `memory/`)
- Les scripts d'itération (validator, dashboard, summarizer) doivent **ignorer**
  les symlinks `workspace` (utiliser `find -P` ou `! -type l`, ou `cfg.iter_projects()`
  qui filtre déjà les symlinks) pour ne pas se perdre dans le code
- Les deux symlinks pointent en chemins **absolus** (les paths workspace/PM ne sont
  pas systématiquement co-localisés ; `realpath` doit fonctionner depuis n'importe où)

**Résolution de chemins cross-tree** (ex: cascade vers le client) :
Ne pas utiliser `.mmi-pm/../../` (résolution logique non fiable des symlinks). Utiliser
la lib + le champ `client:` du frontmatter de `project/overview.md` :

```python
client_dir = cfg.path("entity", entity=client_slug)
```

### Aspects — cahier des charges dynamique

Le **cahier des charges** d'un client ou d'un projet est éclaté en plusieurs fichiers
(aspects) dans le dossier `client/` ou `project/`. Cette approche évite le fichier
monolithique illisible et permet d'enrichir progressivement la connaissance du périmètre.

**Règles :**
- `overview.md` est **obligatoire** — il porte le frontmatter et un index des aspects
- Tout autre fichier est **optionnel** — sa présence indique que l'aspect est documenté
- L'agent qui charge le contexte lit **tous** les fichiers du dossier `project/` (et `client/`)
- Les templates d'aspects sont dans `templates/aspects/{domaine}/{aspect}.md`

**Cascade des aspects :**
Un aspect peut exister au niveau client ET au niveau projet. L'agent lit les deux.
Le projet précise/surcharge le client sur les points en contradiction.

Exemple :
- `{entity_client_dir}/hosting.md` : "Tous nos sites sont hébergés chez OVH par défaut"
- `{project_dir}/hosting.md` : "Ce projet est sur AWS pour des raisons spécifiques"
→ Pour ce projet, l'agent applique AWS (override).

### Environnements (aspect `environments.md`)

Aspect dédié à la déclaration des environnements d'exécution d'un projet (dev, test,
staging, prod, etc.), distinct de `hosting.md` (provider/coûts/DNS).

**Format** : frontmatter avec liste `environments[]`, chaque entrée décrivant un env.
Voir `templates/aspects/common/environments.md`.

**Énumération des noms d'env standard :**
`local | dev | test | staging | prod | demo | qa | sandbox | <nom-custom-kebab-case>`

> **`staging` et `preprod` sont un seul et même environnement** (fusionnés en v1.36.0) :
> l'env de non-régression déployé depuis `integration_branch` avant MEP. **Valeur
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
- `secrets_source` : pointeur Vaultwarden (cf. section "Gestion des secrets")
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
(sauf si `test_url` est explicitement surchargé).

**Tableau `env_vars[]`** : liste des variables d'environnement attendues (noms,
description, dans quels envs elles existent). **Sans les valeurs** — celles-ci sont
soit dans le `.env` local (gitignored), soit dans Vaultwarden via `secrets_source`.

### Gestion des secrets — Vaultwarden

Les credentials sensibles (mots de passe, tokens, clés) **ne sont jamais commités**,
ni dans le repo PM public, ni dans le repo projets privé. Ils vivent dans une instance
Vaultwarden interne (https://vault.iprospective.fr), et sont **référencés** dans les
documents PM via un URI dédié.

**URI :**
```
vaultwarden://<organization>/<collection>/<item>
```

Ex : `vaultwarden://iprospective/calicote-agents/prod-db`.

**Architecture du vault** (chez iprospective) :

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
| Déverrouillage | `scripts/unlock-vault.sh` (demande master password de karl, jamais stocké) | toi (humain) |
| Résolution d'un secret | `scripts/resolve-secret.sh "vaultwarden://..."` | agent / script |
| Verrouillage manuel | `scripts/lock-vault.sh` | toi |

Le déverrouillage démarre un daemon local `vault-agentd.py` qui :
- garde la session BW **en mémoire** uniquement (pas de fichier, pas même tmpfs)
- expose un socket Unix `/run/user/$UID/vault-agentd.sock` (chmod 600)
- se verrouille automatiquement après inactivité (`VAULT_IDLE_TIMEOUT`, défaut 8h)
  et/ou à une heure fixe (`VAULT_LOCK_AT_HOUR`, défaut 23h)

**Règles strictes :**
1. Un agent ne demande **jamais** le master password ; si `resolve-secret.sh` renvoie
   "session expirée", l'agent doit dire à l'humain "lance `unlock-vault.sh`" et attendre
2. Les secrets résolus **ne sont jamais loggués**, jamais écrits sur disque, jamais
   inclus dans un commit ou un transcript
3. La rotation du token API de `karl` est trimestrielle (ou immédiate en cas de doute)
4. Les agents 24/7 (cron nocturne, n8n) ne peuvent fonctionner que dans la fenêtre
   d'unlock manuel ou via un sous-scope dédié explicitement autorisé (cas particulier)

**Variables d'env requises** (dans `.env` local) :
- `VAULT_URL` (URL Vaultwarden)
- `BW_CLIENTID` + `BW_CLIENTSECRET` (API key de karl, pas de master password)

**Convention dans `environments.md` et autres aspects** : utiliser
`secrets_source: vaultwarden://<org>/<coll>/<item>` comme pointeur, jamais la valeur
brute. Documenter dans `client/security.md` (ou équivalent) la liste des items
référencés et leur rôle, pour audit humain.

## Cascade et héritage

Le système suit une cascade à 3 niveaux : **client → projet → tâche**.

**Règles :**
- Par défaut, les valeurs d'un niveau parent sont héritées par tous ses enfants
- Un niveau enfant peut **surcharger** une valeur en la redéfinissant explicitement
- Les sections de texte (Description, Structure...) ne se surchargent pas — elles s'additionnent

**Champs candidats à l'héritage :**
- `team`, `defaults.priority`, `gitlab.group`, `gitlab.default_branch`
- `redmine.instance`, contraintes globales

**Lecture du contexte par un agent (worker, summarizer, reviewer) :**
```
1. Système    : NORMS.md + agents/worker-common.md + agents/worker-{role}.md
2. Client     : {entity_client_dir}/*.md + {entity_memory_dir}/*.md
3. Projet     : {project_dir}/*.md + {project_memory_dir}/*.md
4. Tâche      : paths.task_file + paths.task_log_file
```

(Chemins résolus via `pm.config.yml` — par défaut : `{projects_root}/clients/{C}/...`)

Chaque niveau **complète** ou **surcharge** le précédent selon les règles ci-dessus.

## Nommage des fichiers

| Élément | Format |
|---|---|
| Tâche | `RM{id}_{titre-en-kebab-case}.md` |
| Journal | `RM{id}_{titre-en-kebab-case}.log.md` |
| Overview projet | `project/overview.md` |
| Overview client | `client/overview.md` |

## Lien Redmine ↔ MD (obligatoire)

Toute entité du système (tâche, projet) **doit** être reliée à son équivalent Redmine.
Cette règle est vérifiée par le validateur.

### Tâche

- `redmine_id: <int>` est **obligatoire** dans le frontmatter
- Le nom de fichier `RM{id}_{titre}.md` **doit correspondre** à `redmine_id`
  (cohérence vérifiée par le validateur)
- Pas de tâche MD sans ticket Redmine préexistant

### Projet

- `redmine.project_id: <slug>` est **obligatoire** dans `project/overview.md`
- `redmine.subprojects: [slug, slug, ...]` est optionnel — liste les sous-projets
  Redmine rattachés (utile quand plusieurs sous-projets concernent ce même projet MD)

### Création d'un projet PM ↔ Redmine

À la création d'un nouveau projet PM, le flow doit garantir un mapping **1 ↔ 1** entre
projet PM et projet Redmine. Étapes (à automatiser dans `pm project init`) :

1. **Lister** les projets Redmine accessibles via l'API (`GET /projects.json`)
2. **Vérifier l'existence** d'un projet Redmine avec un identifier candidat
3. **Vérifier l'unicité** d'usage côté PM : itérer `cfg.iter_projects()` (ou
   `grep -r 'redmine.project_id:' "$(cfg.path("entities_dir"))"`) pour s'assurer
   qu'aucun autre projet PM ne référence déjà cet identifier
4. **Trois cas** :
   - Identifier candidat dispo côté Redmine ET non utilisé côté PM → proposer de
     **créer** le projet Redmine (`POST /projects.json`)
   - Identifier existant côté Redmine ET non utilisé côté PM → proposer de **réutiliser**
   - Identifier existant côté Redmine ET déjà utilisé côté PM → bloquer + indiquer le
     projet PM qui l'utilise déjà, demander un autre slug

Le mapping inverse (Redmine identifier → projet PM) doit toujours être unique. Si un
même projet Redmine doit servir plusieurs projets MD, c'est probablement une erreur de
modélisation côté PM (probablement deux projets distincts à créer).

**Memberships par défaut sur un nouveau projet Redmine** (instance iprospective —
`tasks.iprospective.fr`) :

À la création d'un projet Redmine via API (`POST /projects.json`), ajouter
systématiquement ces deux memberships via `POST /projects/<id>/memberships.json` :

| Groupe Redmine | id | Rôle | role_id |
|---|---|---|---|
| `Admin` | 49 | `Manager` | 3 |
| `iProspective` | 70 | `Intervenant` | 7 |

Justification :
- `Admin` en Manager garantit que tu (Mathieu) gardes les pleins droits sur le projet,
  sans dépendre d'une appartenance individuelle
- `iProspective` en Intervenant permet aux comptes de l'équipe (humains + agents :
  `claude-chefproj-1`, `karl@`, etc.) de voir et collaborer sur le projet sans devoir
  les ajouter un par un à chaque projet

Le futur `pm project init` (TODO 003) devra automatiser ces deux ajouts.
À faire manuellement en attendant, via l'UI Redmine → Settings → Members → Add.

Payload API pour automation :
```bash
# Admin (group_id=49) en Manager (role_id=3)
curl -X POST -H "Content-Type: application/json" -H "X-Redmine-API-Key: $REDMINE_API_KEY" \
  -d '{"membership":{"user_id":49,"role_ids":[3]}}' \
  "$REDMINE_URL/projects/<project_id>/memberships.json"
# iProspective (group_id=70) en Intervenant (role_id=7)
curl -X POST -H "Content-Type: application/json" -H "X-Redmine-API-Key: $REDMINE_API_KEY" \
  -d '{"membership":{"user_id":70,"role_ids":[7]}}' \
  "$REDMINE_URL/projects/<project_id>/memberships.json"
```

### Tâches de bootstrap (`templates/bootstrap-tasks/`)

À la création d'un projet PM, certaines tâches **récurrentes de setup** doivent être
créées pour ne pas oublier les fondations : Vaultwarden, repos git, environnements,
stack, etc. Ces tâches viennent de templates dans `templates/bootstrap-tasks/`.

**Templates standards** (présents dans `templates/bootstrap-tasks/`) :

| ID | Titre | Coché par défaut |
|---|---|---|
| `001-secrets-vaultwarden` | Setup items Vaultwarden + remplir `secrets_source` des envs | ✅ |
| `002-git-repos` | Configurer remote git du workspace, premier push | ✅ |
| `003-environnements` | Documenter envs (dev/test/staging/prod) dans `environments.md` | ✅ |
| `004-stack` | Rédiger `project/stack.md` (langages, framework, dépendances) | ☐ |
| `005-deployment` | Rédiger `project/deployment.md` (CI/CD, rollback) | ☐ |
| `006-testing` | Rédiger `project/testing.md` (stratégie de tests) | ☐ |
| `007-monitoring` | Rédiger `project/monitoring.md` (logs, métriques, alertes) | ☐ |
| `008-infra-analysis` | Analyse de l'infra : inventaire, état, risques (`docs/infrastructure.md`) | ✅ *(projets infra uniquement)* |

> **Projets infra → ticket d'analyse par défaut (v1.30.0).** Tout projet de nature
> **infrastructure** (slug/nom « infra », ou aspect `hosting`/`infrastructure` — qui
> gère des serveurs/hyperviseurs/réseau/stockage plutôt qu'une seule application) doit
> par défaut porter un **ticket d'analyse de l'infra** : état des lieux matériel,
> stockage (disques + SMART, pools/RAID), charges hébergées, monitoring, et une section
> **anomalies** d'où découle **un ticket dédié par anomalie significative**. C'est le
> rôle du template `008-infra-analysis`, proposé **coché** sur ces projets et non
> applicable aux projets purement applicatifs. Le livrable est un document vivant
> (`docs/infrastructure.md` dans le workspace, ou aspect `project/hosting.md`), mis à
> jour à chaque intervention notable.

**Flow d'instanciation** (via `scripts/pm-project-bootstrap.py`) :

1. Détecter les templates **applicables** au projet (état du frontmatter overview,
   présence des aspects, etc.)
2. **Proposer** la liste à l'humain (interactif) — les 3 premiers cochés par défaut,
   les autres non
3. L'humain peut **décocher** ou **cocher** des templates supplémentaires
4. L'humain peut **bypasser** complètement (option `--yes`) ou skip un template
   spécifique (champ frontmatter `bootstrap.skip[]`)
5. Pour chaque template retenu :
   - Créer un ticket Redmine dans `redmine.project_id` du projet
   - Instancier `tasks/RM<id>_<slug>.md` depuis le template (frontmatter rempli)
   - Initialiser le `.log.md`

**Frontmatter `project/overview.md` enrichi pour suivre le bootstrap :**

```yaml
bootstrap:
  skip: []          # IDs de templates explicitement skippés (jamais proposés)
  done: []          # IDs de templates déjà appliqués (= tâche créée)
```

Si un template est dans `done[]`, il n'est plus reproposé (même si le critère de
détection le rend applicable). Si dans `skip[]`, idem. Le flow d'instanciation
remplit `done[]` automatiquement.

**Convention `default_checked` dans les templates :**

Chaque template porte un champ frontmatter `default_checked: true|false` qui
détermine s'il est coché par défaut dans le picker interactif.

### Workflow multi-tour (reprise après notes du demandeur)

Quand un ticket revient à un worker (réattribution, ou statut passe à `a_corriger`),
le worker doit ne traiter que les **nouveautés** depuis sa dernière vue du ticket.

Champs du frontmatter de la tâche :
- `redmine_last_journal_id: <int>` — id du dernier journal Redmine consulté
- `redmine_last_checked_at: <str iso>` — timestamp du dernier check

Protocole de reprise :
1. `scripts/redmine-fetch-updates.py --issue <id>` → affiche tous les journaux
   postérieurs à `redmine_last_journal_id`, et met à jour ce champ
2. Lire les nouvelles notes + changements d'attributs (status, assignation, priorité…)
3. Décider : corrections à faire ? livrables à compléter ? ticket déjà résolu ?
4. Appliquer le travail demandé selon le protocole worker standard
5. Resoumettre via `redmine-post-note.py --norms-status a_tester_demandeur` (qui
   réattribue automatiquement au demandeur)

Le champ `redmine_last_journal_id` est initialisé par `redmine-fetch-task.py` à la
**dernière entrée existante** au moment du fetch, pour que le worker ne traite que
ce qui se passe **après** sa prise en charge.

**Persistance dans le journal** : `redmine-fetch-updates.py` appende chaque nouveau
journal Redmine récupéré au fichier `.log.md` de la tâche (append-only, conforme
NORMS). Format d'entrée :

```markdown
## YYYY-MM-DDTHH:MM — Redmine #<journal_id> — <auteur Redmine>
Source : Redmine (sync via redmine-fetch-updates)

Changements :
- `field` : `old` → `new`
- ...

Note (verbatim) :
> ligne 1
> ligne 2
```

Le worker peut ainsi retrouver l'historique complet des échanges (côté Redmine ET
côté agent) en relisant simplement le `.log.md`, sans avoir à re-fetcher l'API.

### Synchronisation des statuts MD ↔ Redmine (obligatoire)

**Tout changement de `status` dans le frontmatter d'une tâche doit être répercuté
sur le ticket Redmine correspondant**, dans le même cycle de travail.

L'agent (ou l'orchestrateur) qui modifie le `status` MD doit :
1. Mettre à jour le frontmatter (`status`, `status_history`, `updated`)
2. Appender l'événement dans `.log.md`
3. Poster une note Redmine + changer le `status_id` correspondant
   (typiquement via `scripts/redmine-post-note.py --norms-status <statut>`)

**Demandeur effectif = `author_id` natif Redmine** (cf. RM1735) :

Le ticket porte son demandeur via le champ standard `author_id`. À la création
par `pm-task-add.py`, un PUT immédiat ajuste `author_id` :
- **Par défaut** → Manager IA (`pm.config.yml :: ia.default_manager.redmine_id`)
- **Avec `--initiator-agent`** → karl (id=79) : audits autonomes, bootstrap
  automatique, tâches initiées par un agent

Le CF `Demandeur` (id=12) est **déprécié** (cf. RM1739 pour la suppression
définitive sur l'instance). Plus aucun script ne le consulte.

**Règle d'attribution Redmine** :
- Passage en `etude_chiffrage_a_valider` → ré-attribuer au **demandeur** (author) :
  l'étude / CDC / chiffrage sont finis et soumis à sa validation. **Même résolveur
  que `a_tester_demandeur`** (author ≠ karl → author ; author == karl → Manager IA).
  Appliqué automatiquement par `pm-task-status-update.py`.
- Passage en `a_tester_dev` → ré-attribuer à un **testeur ≠ le dev** (agent ou
  humain), pour un test indépendant en env `test`. Manuel via `--assign-to <id>`
  pour l'instant ; l'orchestrateur routera vers un worker-test quand il sera en place.
- Passage en `a_tester_demandeur` → ré-attribuer au **demandeur** (author).
  Résolveur appliqué par `pm-task-status-update.py` :
  1. `author == karl` (cas légitime --initiator-agent) → **Manager IA**
  2. `author ≠ karl` avec email accessible → cet `author`
  3. fallback (email inaccessible) → Manager IA
- Passage en `a_mep` → ré-attribuer au **responsable MEP / intégration** (par défaut
  Manager IA ou orchestrateur ; configurable par projet).
- Passage en `en_mep` → ré-attribuer au **testeur humain** chargé de la vérification
  en preprod (étape 3 du workflow MEP, cf. § Cycle dev → test → MEP).
- Passage en `a_corriger` → ré-attribuer au **worker** précédent (manuellement pour
  l'instant via `--assign-to <id>`, automatisé quand l'orchestrateur sera en place).
- Passage en `en_pause` → **conserver** l'attribution courante (la tâche reste
  possédée, juste sortie des files actives).
- Passage en `ferme` → conserver l'attribution courante.

> Note : `a_tester_verifier` (≤ v1.18.0) est **déprécié**, remplacé par le couple
> `a_tester_dev` / `a_tester_demandeur`. Les scripts l'acceptent encore en lecture
> et le normalisent vers `a_tester_demandeur` (rétrocompat).

**Manager IA** (cf. RM1734) : humain qui supervise les agents (karl + futurs),
reçoit la notif mail à chaque livraison, se voit assigner les tickets
`a_tester_demandeur` quand l'auteur est karl. Configuré dans `pm.config.yml` :

```yaml
ia:
  default_manager:
    redmine_id: 5
    email: mathieu@iprospective.fr
    name: Mathieu Moulin
```

V2 prévue : cascade par projet (`ia.managers:` par `paths.project`) et/ou
champ `ia_manager:` dans le frontmatter de `project/overview.md`.

### Prise en charge d'une tâche : `en_cours` ⇒ auto-assignation (obligatoire) — v1.12.0

**Règle** : un agent qui commence à travailler sur une tâche doit, dans le **même
mouvement** :

1. Passer le `status` de la tâche à `en_cours` (côté Redmine + frontmatter MD + log)
2. **S'assigner le ticket Redmine** (champ `assigned_to`) si ce n'est pas déjà le cas

Les deux opérations sont **indissociables**. Une tâche `en_cours` sans
`assigned_to` cohérent est un état invalide : `en_cours` signifie « un agent
nommément identifié est en train de faire le travail maintenant ». Pas
d'`en_cours` flottant.

Cette règle vaut **même hors orchestrateur** (mode interactif Claude Code) : si
un humain demande à l'agent de bosser sur RM1234 et que le ticket n'est ni à
`en_cours` ni assigné à l'agent, l'agent fait lui-même les deux opérations avant
de démarrer le travail effectif.

**Symétrie avec la `Vérification initiale` de [worker-common.md](../agents/worker-common.md)** :
ce qu'un worker orchestré vérifie passivement (status + assigné à soi), un agent
en mode interactif l'établit activement au démarrage.

**Implémentation** (état v1.12.0) : `pm-task-status-update.py` ne couple pas
encore status + assignation. En attendant un patch, l'agent enchaîne
manuellement :

```bash
./pm-task-status-update.py <RM-id> en_cours --note "Prise en charge"
./redmine-post-note.py --issue <RM-id> --note "Auto-assignation <agent>" --assign-to <user-id>
```

→ TODO scripts : `pm-task-status-update.py` doit, quand la cible est `en_cours`,
auto-assigner au user Redmine de l'agent courant (résolu via
`pm.config.yml :: agents.<id>.redmine_id`, défaut karl=79).

**Mapping NORMS → Redmine (instance iprospective)** — après consolidation RM1742 :

Statut Redmine (un seul terminal `Fermé`) :

| NORMS | Redmine | id |
|---|---|---|
| `nouveau` | Nouveau | 1 |
| `a_etudier_chiffrer` | A étudier / Qualifier | 8 |
| `etude_chiffrage_en_cours` | Etude/CDC en cours | 14 |
| `etude_chiffrage_a_valider` | Etude/CDC à valider | 21 |
| `a_faire` | A Faire | 12 |
| `en_cours` | En cours | 2 |
| `a_tester_dev` | A tester/vérifier dev | 19 |
| `a_tester_demandeur` | A tester/vérifier demandeur | 9 |
| `a_mep` | Résolu/Validé/A MEP | 3 |
| `en_mep` | MEP/Tester en preprod | 20 |
| `en_pause` | Attente retour / en pause | 13 |
| `a_corriger` | A corriger/finir | 11 |
| `ferme` (toutes raisons) | Fermé | **18** |

`a_tester_verifier` (déprécié) → lu comme `a_tester_demandeur` (id 9).
`a_mep` (Résolu/Validé/A MEP, id 3) est un statut **non terminal** (validé par le
demandeur, mergé dans l'intégration, en file de MEP) — à ne pas confondre avec
`ferme`.

`nouveau` (Nouveau, id 1) est le **statut d'entrée** : `pm-task-add.py` crée par
défaut un ticket en `nouveau` (ticket déposé, non encore trié/engagé), avec
`author_id` posé mais **sans `assigned_to`** (pas encore pris en charge). Le tri
vers `a_faire` / `a_etudier_chiffrer` / `en_cours` se fait ensuite (manuellement
ou à la création via `pm-task-add.py --status <statut>`, qui crée en `nouveau`
puis transitionne via `pm-task-status-update.py` pour bénéficier du couplage
NORMS — assignation, note, `status_history`). Un ticket reste légitimement en
`nouveau` tant qu'il n'a pas été engagé ; ce n'est pas un état invalide.

Raison de fermeture (CF `Raison Fermé`, id=11, format enumeration) — valeurs :

| NORMS `close_reason` | CF Raison Fermé | value_id |
|---|---|---|
| `resolu` | Résolu | 10 |
| `wont_fix` / `hors_perimetre` | Rejeté | 11 |
| `abandonne` | Abandonné | 12 |
| `doublon` | Déjà existant | 13 |
| `invalide` | Pas un bug / rien à faire | 14 |

Note : les anciens statuts terminaux `Résolu/Fermé` (5), `Rejeté` (6),
`Pas un bug / Déjà existant` (7), `Abandonné` (10) sont **dépréciés** —
à désactiver/supprimer en UI Redmine. Attention à ne pas les confondre avec le
nouveau `Résolu/Validé/A MEP` (id 3, `a_mep`), qui est **non terminal**.

### Mise à jour de la description du ticket Redmine (obligatoire) — v1.13.0

La **description** d'un ticket Redmine (le corps principal, distinct des notes
de journal) est un document **vivant** : ce n'est pas un message figé à la
création, mais l'état courant de la demande. L'agent doit la maintenir à jour
chaque fois que son contenu cesse de refléter la réalité.

**Quatre déclencheurs obligent à mettre à jour la description** :

1. **La description contient des informations d'état qui ont changé** — par
   exemple un statut interne décrit en prose (« En attente de validation
   client », « bloqué par X »), une URL d'environnement de test, une version
   cible, une décision provisoire. Si la description affirme quelque chose qui
   n'est plus vrai, elle doit être réécrite, pas seulement contredite dans une
   note.
2. **La description contient une liste de tâches / une checklist** dont l'état
   évolue (cases cochées Markdown `- [ ]` / `- [x]`, sous-objectifs, critères
   d'acceptation, étapes restantes). À chaque progression, l'agent met à jour
   les cases ou items concernés **dans la description elle-même**, pas
   uniquement dans une note. La description sert de tableau de bord ; les notes
   servent à l'historique.
3. **Demande explicite** du demandeur ou d'un autre intervenant (« mets à jour
   la description avec X », « ajoute Y dans la description », reformulation
   demandée du périmètre, etc.).
4. **Modification substantielle de la demande en cours de travail** — quand
   le demandeur change un nom de chemin, un identifiant, une cible, ou
   ajoute/retire un item du périmètre **après** que la description a été
   rédigée. Le re-cadrage doit être répercuté dans la description (pas
   seulement traité dans une note de journal), car la description sert de
   référence pour la vérification finale. Ex : la description liste
   `old/ → erp_old/old/` mais le demandeur demande ensuite `erp_old/dev/` —
   réécrire la description avec `erp_old/dev/`, et accompagner d'une note
   « Description mise à jour suite re-cadrage : `erp_old/old` → `erp_old/dev` ».
   Ne **pas** se contenter d'une note « fix complémentaire » : si quelqu'un
   relit la description plus tard, il doit y voir l'état final, pas
   l'état initial.

**Note de journal accompagnante** : toute mise à jour de description doit être
accompagnée d'une note Redmine résumant **ce qui a changé** et **pourquoi**
(« Description : coché items 3 et 4 de la checklist (livraison faite, doc à
jour) »). Cela préserve la traçabilité — Redmine ne diff pas les descriptions
dans l'UI standard.

**Symétrie avec les notes** :
- **Note** = événement daté, append-only, raconte le « quoi s'est passé ».
- **Description** = état courant, mutable, raconte le « où on en est ».

Une checklist cochée uniquement dans une note (et pas dans la description) est
invisible dès qu'on scrolle ; une décision d'état figée dans la description
initiale et contredite par 12 notes successives est illisible. Les deux médias
sont complémentaires et **les deux doivent être tenus à jour**.

**% réalisé (`done_ratio`) au fil de l'eau** — v1.16.0 : l'agent maintient le
pourcentage de réalisation du ticket (`done_ratio` Redmine ↔ `completion_pct` MD)
**au fur et à mesure**, pas seulement à la clôture. La valeur se dérive :
- du **ratio de cases cochées** de la checklist quand il y en a une
  (`cochées / total`, arrondi) — c'est la règle par défaut ;
- sinon de l'**évaluation de l'agent** (avancement estimé du travail).

Le changement de `done_ratio` étant **journalisé nativement** par Redmine (comme
le statut, cf. v1.15.0), il ne donne **pas** lieu à une note dédiée. Une note
n'accompagne que les changements de **description** (texte/checklist), que Redmine
ne diff pas. Cocher un item de checklist EST une modification de description → note ;
faire passer le `done_ratio` de 50 à 75 → pas de note.

**Implémentation** (état v1.16.0) :
- **`pm-task-description-update.py <rm-id>`** : coche/décoche la checklist
  (`--check 1,2`, `--uncheck 3`, `--check-all`), met à jour `done_ratio`
  (`--done-ratio auto` depuis la checklist, ou un entier), ou remplace toute la
  description (`--set-from-file`). PUT Redmine (`description` + `done_ratio` +
  `notes` si la description a changé) + sync MD (`completion_pct` + checklist du
  corps) + append `.log.md`. C'est le wrapper de référence.
- **`pm-task-status-update.py`** refuse de passer une tâche en `a_tester_demandeur`,
  `a_mep` ou `ferme:resolu` s'il reste des items de checklist **non cochés** dans la
  description (`--allow-unchecked` pour outrepasser si c'est volontaire). Garde-fou
  pour ne pas livrer/clore avec une checklist non tenue à jour.

### Flux de création de tâches (v1.5.0)

Deux flux supportés :

**a) Création depuis Redmine** (workflow humain ou agent)
1. Un humain (ou un agent) crée le ticket dans Redmine et l'assigne à un agent IA
2. L'orchestrateur détecte l'assignation, génère `paths.task_file` (résolu via
   `pm.config.yml` à partir de l'entité et du projet)
3. Le worker assigné prend la tâche en charge

**b) Création depuis CLI dans le workspace projet** (à implémenter — voir [TODO/003](../TODO/003-pm-cli.md))
1. Depuis le workspace de code, l'utilisateur lance `pm task create --type ... --title "..."`
2. Le script crée le ticket Redmine, récupère l'ID
3. Génère le fichier MD dans `.mmi-pm/tasks/RM{id}_*.md` (le symlink pointe vers
   `paths.project`)
4. Commit + push automatique

Le sens inverse pur (MD → Redmine sans ticket préexistant) n'est pas implémenté en
v1.5 — voir [PISTES.md](../PISTES.md).

## Schéma frontmatter — Tâche

Voir [templates/task.md](../templates/task.md) pour le template complet.

### Champs obligatoires
`schema_version`, `redmine_id`, `title`, `type`, `creator`, `status`, `priority`, `created`

### Champs conditionnels
- `bug.*` — uniquement si `type: bugfix`
- `git.*` — si développement impliqué
- `test_url` — si environnement de test disponible
- `deploy_actions` — si déploiement nécessaire
- `close_reason` — obligatoire quand `status: ferme`
- `requires_agent_test` — `default` (défaut) | `oui` | `non` | `demander` : conditionne la
  passe agent-testeur en fin de dev (cf. § « Passe agent-testeur indépendante »). Mappé sur
  le CF Redmine 27. Absent ⇔ `default`.

## Valeurs énumérées

### type
`audit` | `feature` | `bugfix` | `refactoring` | `documentation` | `security` | `performance` | `infrastructure` | `database` | `design` | `research` | `maintenance` | `assistance`

### status
`a_etudier_chiffrer` | `etude_chiffrage_en_cours` | `etude_chiffrage_a_valider` | `a_faire` | `en_cours` | `a_tester_dev` | `a_tester_demandeur` | `a_mep` | `en_mep` | `en_pause` | `a_corriger` | `ferme`

`a_tester_verifier` est **déprécié** (≤ v1.18.0) — alias en lecture de
`a_tester_demandeur`, normalisé par les scripts.

### priority
`low` | `normal` | `high` | `urgent`

### close_reason
`resolu` | `abandonne` | `doublon` | `wont_fix` | `invalide` | `hors_perimetre`

### bug.reproducibility
`always` | `often` | `sometimes` | `rarely` | `never`

### estimate.difficulty
`low` | `medium` | `high` | `critical`

### pistes.type
`automation` | `amélioration` | `sécurité` | `performance` | `intégration` | `documentation`

### pistes.effort
`low` | `medium` | `high`

### roi.immediate_benefit / roi.monthly_benefit
`1` (négligeable) → `5` (critique)

### target_env
`null` | `local` | `dev` | `test` | `staging` | `prod` | `demo` | `qa` | `sandbox` | `<custom-kebab-case>`

Doit correspondre à un `environments[].name` du `project/environments.md` (ou
`client/environments.md` en cascade). Custom autorisé si le projet a un env spécifique
(`staging-eu`, `prod-canary`…). `preprod` reste accepté comme **alias** de `staging`
(cf. § Environnements) mais `staging` est la valeur canonique à privilégier.

## Journal (fichier .log.md)

Format append-only — ne jamais modifier rétroactivement. Chaque entrée :

```markdown
## 2026-04-26T14:32 — agent-scraper (claude-sonnet-4-6)
Tokens : 3 200 | Durée : 15 min

Résumé de ce qui a été fait...
```

## Collaboration multi-agents

### Principe fondamental

**Redmine est le mutex. Les fichiers MD sont le contexte de travail.**

L'assignation d'un ticket Redmine à un agent lui confère la **propriété exclusive** du fichier MD correspondant. Aucun autre agent ne doit écrire dans ce fichier tant que l'assignation est active.

L'inférence LLM est déjà distribuée par nature (appels API vers Anthropic). Ce qui doit être coordonné, c'est uniquement l'accès aux fichiers.

### Rôles des agents

**Orchestrateur**
- Un agent coordinateur unique par périmètre actif
- Surveille les tickets en attente (`a_faire`) dont les dépendances sont satisfaites
- Assigne les tickets aux workers via l'API Redmine (opération atomique)
- Seul écrivain sur les fichiers de tâches parentes (à tous les niveaux)
- Met à jour `completion_pct` des parents quand leurs enfants terminent (propagation bottom-up)
- Déclenche le testeur/reviewer quand une tâche passe en `a_tester_dev`
- Route les tickets vers le bon worker selon le champ `type`

**Workers (agents spécialisés)**

| Type de tâche | Agent |
|---|---|
| `feature` / `bugfix` / `refactoring` / `security` / `performance` | worker-dev |
| `audit` / `research` / `documentation` / `assistance` / `maintenance` | worker-analyst |
| `database` | worker-db |
| `infrastructure` | worker-infra |
| `design` | worker-design |

- Propriétaire exclusif de leur fichier de tâche assignée
- Lecture seule sur tous les autres fichiers MD
- Append-only sur tous les `.log.md`

**Reviewer**
- Déclenché par l'orchestrateur sur `a_tester_dev` (test indépendant, par un agent
  ≠ celui qui a fait le dev)
- Lit le fichier de tâche + le `.log.md` + les critères d'acceptation
- Valide → `a_tester_demandeur` (passe la main au demandeur ; ne clôt pas — la
  clôture passe par la validation demandeur puis la MEP, cf. § Cycle dev → MEP)
- Rejette → `a_corriger` avec note obligatoire dans le `.log.md`

### Règles d'écriture

| Fichier | Orchestrateur | Worker assigné | Autres workers | Reviewer |
|---|---|---|---|---|
| `RM{id}.md` (tâche assignée) | lecture | **R+W** | lecture | lecture |
| `RM{id}.md` (tâche parente) | **R+W** | lecture | lecture | lecture |
| `RM{id}.log.md` | append | append | lecture | append |
| `project.md` | **R+W** | lecture | lecture | lecture |
| `NORMS.md` | lecture | lecture | lecture | lecture |

### Protocole de prise en charge d'une tâche

```
1. Orchestrateur lit les tickets Redmine status=a_faire
2. Pour chaque ticket éligible :
   a. Vérifie que tous les tickets dans depends_on sont ferme
   b. Sélectionne le worker adapté au type de tâche
   c. Assigne le ticket Redmine au worker via API (atomique)
      → succès   : l'agent est propriétaire, continuer
      → conflit  : ticket déjà pris, passer au suivant
3. Worker reçoit l'assignation
4. Worker lit son fichier RM{id}.md
5. Worker met à jour le frontmatter :
   - status: en_cours
   - status_history: + nouvelle entrée (at, by, model)
   - updated: timestamp courant
6. Worker travaille, appende ses logs dans RM{id}.log.md
7. À la fin, worker met à jour son fichier :
   - completion_pct, outputs, updated, status_history
8. Worker passe le ticket Redmine en a_tester_dev
9. Orchestrateur détecte le changement, déclenche le testeur/reviewer
10. Reviewer valide → a_tester_demandeur (puis demandeur → a_mep → MEP), ou renvoie en a_corriger
11. Si validé : orchestrateur propage la completion au parent
```

### Sous-tâches multi-niveaux

Les sous-tâches s'imbriquent sur autant de niveaux que nécessaire. La règle est uniforme : **l'orchestrateur est le seul écrivain sur toute tâche ayant des enfants**, quel que soit le niveau.

```
RM1000  (niveau 0 — racine)        → orchestrateur
  ├── RM1001  (niveau 1 — parent)  → orchestrateur
  │     ├── RM1002  (niveau 2)     → agent-A
  │     └── RM1003  (niveau 2)     → agent-B
  └── RM1004  (niveau 1 — parent)  → orchestrateur
        ├── RM1005  (niveau 2)     → agent-C
        └── RM1006  (niveau 2)     → agent-D
```

**Propagation du `completion_pct` :**
- Une leaf termine → orchestrateur recalcule le `completion_pct` de son parent immédiat
- Si le parent est complet → orchestrateur propage au grand-parent
- Propagation bottom-up jusqu'à la racine

**Règle :** un nœud parent passe en `ferme` uniquement quand **tous ses enfants directs** sont `ferme`.

**Parallélisme :** les agents travaillant sur des leaves de branches différentes s'exécutent simultanément sans coordination entre eux. Seul l'orchestrateur synchronise au niveau des parents.

### Protocole optimistic locking

Filet de sécurité contre les écritures simultanées accidentelles. Doit se déclencher rarement si les règles de propriété sont respectées.

```
1. Agent lit le fichier, note la valeur courante de updated (T1)
2. Agent prépare ses modifications
3. Agent relit le champ updated avant d'écrire
4. Si updated ≠ T1 → collision détectée → re-lire le fichier et recommencer
5. Si updated = T1 → écrire et mettre updated à T2 (timestamp courant)
```

Ce protocole s'applique à tous les fichiers `.md` (jamais aux `.log.md` qui sont append-only).

### Règles du journal (.log.md)

- **Append-only** : on n'efface jamais, on n'édite jamais une entrée existante
- Tout agent peut appender, même en lecture seule sur la tâche
- En cas d'écriture simultanée, l'ordre des entrées n'est pas garanti — c'est acceptable
- Pas d'optimistic locking sur les `.log.md` (append = pas de perte de données)

Format imposé pour chaque entrée :

```markdown
## 2026-04-27T14:32 — agent-dev (claude-sonnet-4-6)
Tokens : 3 200 | Durée : 15 min

Résumé de ce qui a été fait, décisions prises, problèmes rencontrés.
```

#### Journalisation des échanges avec l'humain (obligatoire, au fil de l'eau)

Quand un échange utilisateur ↔ agent porte sur une tâche — arbitrage, décision,
re-cadrage du besoin, retour de test, correction de cap — l'agent **résume** cet
échange et l'appende au `.log.md` de la tâche **au fur et à mesure**, sans attendre
la clôture. On journalise le *pourquoi* des décisions, pas seulement le code produit.

- **Résumer, pas recopier** : une synthèse pertinente, pas le transcript verbatim.
- **Au fil de l'eau** : une entrée par étape significative, datée. Objectif :
  pouvoir reconstituer le fil de la tâche (et les raisons des choix) sans relire
  la conversation d'origine.
- N'enregistrer que ce qui est lié à la tâche ; le bavardage hors-sujet n'a pas
  sa place dans le journal.

#### Unité de traçabilité : l'étape significative (canonique) — v1.23.0

**Référence unique** pour « quand commiter, quand noter ». L'unité de travail
tracée n'est ni le fichier ni la frappe : c'est l'**étape significative** — un
incrément consistant et cohérent (livraison, fonctionnalité, correctif, décision
structurante). On ne commit ni chaque fichier sauvé, ni un seul gros bloc à la
toute fin : on commit **à la frontière d'une étape significative**.

À cette frontière, à partir d'**un seul effort de fond** décliné en deux
granularités, l'agent produit :

1. **Message de commit** — résumé **court** (1 ligne + corps optionnel), langue du repo.
2. **Note Redmine** — résumé **détaillé**, human-readable, destiné au ticket : ce
   qui a été fait/livré et *pourquoi*, + **réf du commit** (SHA + URL GitLab, cf.
   « Référencer un commit ») + **temps + tokens** du delta (cf. § « Journalisation
   par commit »). C'est la trace que les humains lisent.
3. **Entrée `.log.md`** — variante technique de l'agent (détail, décisions) + réf
   commit + métriques, append-only (format ci-dessus). Les humains ne la lisent pas.
4. Si l'étape est une **livraison** : transition de statut + `done_ratio` au même
   moment (cf. §§ dédiés).

> Même synthèse de fond, supports différents (long → note, court → commit,
> technique → log) : pas trois rédactions distinctes.

**Quand poster une note Redmine** — matrice unique, ne pas redéfinir ailleurs :

| Événement | Note ? |
|---|---|
| Commit de **travail / livraison / structurant** (chose dont on veut garder trace) | **Oui** — note détaillée + réf commit + métriques |
| Événement **structurant sans commit** (cahier des charges, réflexion, arbitrage, décision, re-cadrage) | **Oui** — note complémentaire (synthèse, sans réf commit) |
| Commit **trivial / housekeeping** (sync frontmatter, append `.log.md`, fix typo doc PM) | **Non** (sauf `commit_note_level: all`) |
| Simple changement de **statut** ou `done_ratio` | **Non** — Redmine les journalise nativement |
| Mise à jour de **description** (texte/checklist) | **Oui** — cf. § « Mise à jour de la description » (Redmine ne diff pas les descriptions) |

**Niveau de note par commit — configurable** (`pm.config.yml :: traceability.commit_note_level`,
pour calibrer le bruit à l'usage) :
- `work` (défaut) — note pour les commits de travail/livraison/structurants uniquement.
- `all` — note pour **tout** commit rattaché à une tâche (mode test : mesurer le bruit réel).
- `none` — pas de note auto par commit (on conserve `.log.md` + time_entry).

#### Référencer un commit dans une entrée

Toute entrée de journal qui **produit ou modifie du code** doit citer le(s)
commit(s) correspondant(s), pour tracer précisément quelle livraison à quelle étape :

```markdown
Commit: <repo-alias>@<sha-court> — <message court>
        https://gitlab.iprospective.fr/<ns>/<repo>/-/commit/<sha-complet>
```

- La forme **canonique de tracking** est le SHA (≥ 7 caractères) ou, mieux quand le
  repo est sur GitLab, l'**URL de commit complète** (cliquable et résolvable).
- Le frontmatter `git.branch` / `git.mr_url` reste le pointeur *courant* (branche de
  travail, MR ouverte) ; le `.log.md` conserve l'*historique* des commits par étape.
  Pour une référence ponctuelle hors workflow dev, utiliser `refs: [{type: commit, …}]`.
- **Prérequis** : le workspace doit être un dépôt git. S'il ne l'est pas (ex. un
  workspace infra non initialisé), il n'y a pas de commit à référencer — le signaler
  explicitement dans l'entrée plutôt que de laisser un trou.

---

