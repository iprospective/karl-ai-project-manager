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

