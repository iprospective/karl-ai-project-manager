> 📂 **Module `structure-reference` — quand lire ceci :** je résous un chemin PM · j'inspecte l'arbo des repos · je me demande dans quel dépôt committer (code vs structure) · je crée/répare le lien workspace↔PM.
> **Outils :** `pm_paths.PMConfig`, `pm-sync-links`⚠ · **Préchargé par :** worker-infra.

### Anatomie d'un projet — le core, `repos/` et `envs/`

**Un projet est défini par un dossier `.mmi-pm`.** Ce dossier vit dans le **core** du
projet : le dépôt git à la racine du workspace, qui ne **révisionne que `.mmi-pm/`** par
défaut (tout le reste — code, données, démos — y est gitignoré). Le core porte donc la
**définition du projet** (`project/`, `docs/`, `tasks/`, `memory/`) et rien d'autre.

Autour du core, deux dossiers structurent le **code** :

```
<workspace>/                     # = CORE du projet — dépôt git, remote `<Projet>-core.git`
  .mmi-pm/                       # LE projet : project/ docs/ tasks/ memory/  (seul révisionné par le core)
  repos/
    <repo>.git                   # dépôt de CODE, bare — la SOURCE
  envs/
    <repo>-dev                   # WORKTREE tiré de repos/<repo>.git — env d'intégration
    <repo>-rm<RMid>              # WORKTREE de ticket (pm-branch-start --worktree, pm-env-session create)
    <repo>-rm<RMid>-s<seq>       # … suffixé UNIQUEMENT si le canonique sert déjà une autre branche
  …                              # data/, démos, .claude/ … gitignoré par le core
```

Les `envs/*` sont des **worktrees** d'un même dépôt bare `repos/<repo>.git` (cf.
`git-mep` pour le workflow branche/worktree par ticket).

**Nommage des worktrees — convention unique `<repo>-rm<RMid>` (RM2523).** Le nom
dérive du **dépôt** (`repos/<repo>.git`), jamais du worktree depuis lequel on
lance la commande. Le faire dériver du worktree courant — ce que faisait
`pm-branch-start` — concatène son nom à chaque création en cascade et produit des
`<repo>-rm2356-2373-s1-2385-s1-2323-s20-…` (7 cas sur le workspace PM en 2026-08).
Même règle pour le champ `git.repo` du frontmatter : il porte le nom canonique du
dépôt, pas celui d'un worktree ; les valeurs héritées sont normalisées à
l'écriture. Le suffixe `-s<seq>` ne sert qu'à départager deux sessions sur un même
ticket. Un worktree se **résout par sa branche** (`<RMid>-<slug>`), jamais par son
nom deviné — c'est ce qui rend le nommage indifférent à l'outillage.

**Deux dépôts, deux destinations de commit — ne jamais les confondre :**

| Ce que tu commites | Où | Dépôt / remote | Protection de la branche de prod |
|---|---|---|---|
| **Travail / code** (src, tests, config appli) | un **worktree** sous `envs/` | dépôt de code (`repos/<repo>.git` → ex. `worm-web-orm`) | push **personne** → branche de ticket + **MR** |
| **Structure / projet** (tâches, docs, overview, mémoire — tout `.mmi-pm/`) | le **core** (racine du workspace) | dépôt core (ex. `Worm-core.git`) | push **Developer** → écriture **directe** des scripts pm-* |

Les commits de code partent vers le remote du **code** ; les auto-commits PM (`pm-*`,
qui ne touchent que `.mmi-pm/`) partent vers le remote du **core**. **Corollaires
structurels** (invariants pour l'outillage) :

- un dépôt porteur d'un `.mmi-pm` à sa racine **est un core**, **jamais** une cible de
  branche de code — le code se branche dans un worktree `envs/` tiré de `repos/` ;
- un worktree `envs/` n'est **jamais** l'endroit où l'on commite une tâche/doc PM ;
- le marqueur doit être un **dossier réel** : dans un workspace de code, `.mmi-pm` est
  un **symlink** vers le dossier PM centralisé — ce workspace n'est **pas** un core et
  sa branche de prod reste protégée comme du code (RM2440). C'est le test qui distingue
  les deux régimes de protection ci-dessus, implémenté une seule fois dans
  `pm_git.is_core_repo()` et réutilisé par `pm-protect`.

La colonne « protection » est posée par `pm-protect` (cf. `git-mep` § Enforcement
GitLab) ; `allow_force_push=false` s'applique aux **deux** colonnes — quel que soit le
régime, l'historique ne peut que croître.

**Même motif au niveau entité/client** : une entité a son propre **`.mmi-pm-client`**
(core client), porté par son dépôt dédié.

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

### Repo projets (index centralisé)

Racine : `pm.config.yml :: roots.projects_root` (résolu depuis `$PROJECTS_PATH`).
Structure interne définie par les patterns de `paths:` — la représentation
ci-dessous montre la **résolution par défaut**.

> **⚠ Sens du lien inversé — `projects_root` est un INDEX, plus le stockage.**
> Historiquement cette arbo **contenait** les données PM et le `.mmi-pm` de chaque
> workspace y **pointait** (symlink entrant). Le modèle canonique actuel est
> **inversé** : la source de vérité est le **`.mmi-pm` du core** de chaque projet (cf.
> « Anatomie d'un projet » ci-dessus), et chaque
> `projects_root/{entity_projects_dir}/<P>` est un **symlink SORTANT** vers ce
> `.mmi-pm`. `projects_root` est donc un **index** de liens vers les cores — maintenu
> par `mmi-pm index add|rebuild` (reconstruit depuis les emplacements canoniques
> `.mmi-pm` / `.mmi-pm-client`) —, pratique pour que l'orchestrateur scanne tous les
> projets d'un coup (`cfg.iter_projects()`), mais ce **n'est plus** l'endroit où vivent
> les tâches/docs. L'arbre par défaut ci-dessous décrit donc ce que chaque core expose
> **à travers** son lien d'index, pas un stockage central.

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
          {project_dir}/              # = project/project  — CANONIQUES (mathieu-pm, via mmi-pm)
            overview.md               # OBLIGATOIRE — frontmatter + sommaire/index des aspects
            environments.md           # aspect canonique — optionnel (consommé par l'outillage)
          {docs_dir}/                 # = project/docs  — aspects LIBRES (wiki-syncés, group-writable)
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

### Contacts d'un client — `meta.yml :: contacts[]` (v1.69.0, RM2702)

Les personnes d'un client vivent dans le `meta.yml` de son core
(`.mmi-pm-client/meta.yml`), et **uniquement** là. Écriture par
`pm-client-contact.py` (`add` / `list` / `set` / `remove` / `mark-internal` /
`import-redmine`) — jamais à la main (tripwire #1).

```yaml
contacts:
  - last_name: Dupont              # NOM de famille
    first_name: Claire             # prénom
    email: claire@exemple.fr       # identifie la fiche (clé de `set` / `remove`)
    phone: "+33 6 12 34 56 78"     # CHAÎNE : le « + » et les zéros de tête comptent
    role: technique                # owner | decideur | technique | facturation | autre
    title: Gérant                  # fonction EN CLAIR — `role` est une catégorie, pas un titre
    internal: true                 # posé AUTOMATIQUEMENT sur nos propres adresses
```

Deux pièges, tous deux rencontrés en production :

- **`internal`** marque **nos** adresses (`iprospective.fr`…). Le gabarit de création
  en pose une chez **chaque** client : elle n'identifie donc aucun client et ne doit
  jamais servir à l'identifier — router un email entrant sur cette base enverrait tout
  notre courrier chez un client au hasard (cf. routage RM2669).
- Une fiche **entièrement vide** (`{name: "", email: "", role: owner}`) est un résidu
  de gabarit, pas un contact : les outils l'ignorent.

Une **boîte de service** (« Service informatique », « comptabilité ») est un contact
légitime sans nom propre : on renseigne `title` + `email`, sans `last_name`/`first_name`.

Le champ historique `name` (nom complet en un bloc) reste **lu en repli** tant que
toutes les fiches n'ont pas été reprises ; les nouvelles écritures utilisent
`last_name` / `first_name`.

> Un **annuaire de contacts indépendant** des clients (une personne rattachée à
> plusieurs clients/projets, avec un rôle par rattachement) est à l'étude — RM2703.
> Tant qu'il n'existe pas, `contacts[]` reste la source unique.

### Workspace projet — symlinks bidirectionnels `.mmi-pm` ↔ `workspace`

> **⚠ Section legacy — décrit l'ancien modèle (symlink `.mmi-pm` *entrant*).** Le
> modèle canonique actuel est « Anatomie d'un projet » ci-dessus : `.mmi-pm` est un
> **vrai dossier** dans le core, et c'est l'**index** `projects_root` qui porte le
> symlink **sortant**. Le lien inverse `workspace` (côté core) survit sous une forme
> triviale — `.mmi-pm/workspace → ..` (le core EST le workspace). On conserve cette
> section pour les workspaces pas encore migrés et pour la mécanique de résolution
> cross-tree en fin de section, toujours valable.

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
  `.mmi-pm/docs/`, `.mmi-pm/tasks/`) ; un symlink de confort `<workspace>/docs → .mmi-pm/docs`
  expose les aspects libres à la racine du code
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

## Structure des dossiers

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
| `docs_dir` | `{project}/docs` |
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


### Le pont d'onboarding des workspaces (RM1892)

Un agent lancé dans un workspace de code n'a, par défaut, **aucun contexte PM**. Il le
reçoit d'un fichier unique posé à la **racine des workspaces**, lu par remontée
d'arborescence depuis n'importe quel sous-dossier :

| Fichier | Rôle |
|---|---|
| `<racine>/AGENTS.md` | le pont — vendor-neutral (opencode & autres) |
| `<racine>/CLAUDE.md` → `AGENTS.md` | symlink : Claude Code ne lit que `CLAUDE.md`, mais suit les liens |

Il est **conditionnel** : « si ton workspace a un `.mmi-pm`, tu es un worker PM — résous-le,
lis le KERNEL, applique le protocole ; sinon ces règles ne te concernent pas ». Un fichier
par projet serait à la fois redondant et à maintenir ; la remontée d'arborescence couvre
les projets présents **et futurs**.

Ce fichier est **hors git** : c'est un artefact de provisioning, propre à l'instance. Sa
référence versionnée est `templates/workspace-AGENTS.md`, et le déploiement est outillé
(`pm-workspace-bridge.py` — contrôle, `--install`, `--update`). Le bloc délimité
`BEGIN/END INSTANCE` porte ce qui est propre à la machine (chemins, hôtes, transport git) :
`--update` rafraîchit le générique et **préserve ce bloc**, ce qui permet de faire évoluer
l'onboarding sans faire perdre à une instance ce qu'elle sait d'elle-même.
