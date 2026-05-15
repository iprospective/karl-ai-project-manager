# Système de gestion de tâches — iprospective

Système de gestion de projets et tâches conçu pour la collaboration entre humains et agents IA.
Les tâches sont des fichiers Markdown structurés, Redmine est le tracker opérationnel, GitLab assure le versioning.

## Installation

```bash
# 1. Cloner ce repo
git clone git@gitlab.iprospective.fr:iprospective/ai-artificial-intelligence/ai-project-management.git
cd ai-project-management

# 2. Configurer l'environnement
cp .env.example .env
# Éditer .env avec les vraies valeurs (GitLab token, Redmine API key, PROJECTS_PATH...)

# 3. Cloner le repo des projets (chemin défini par PROJECTS_PATH dans .env)
git clone git@gitlab.iprospective.fr:iprospective/ai-projects.git "$PROJECTS_PATH"

# 4. (Optionnel) Surcharger pm.config.yml en local
#    cp pm.config.yml pm.config.local.yml
#    # éditer pour ajuster les chemins/patterns (gitignored)
```

## Démarrage rapide

Tous les chemins ci-dessous sont **logiques** (patterns de `pm.config.yml`).
Leur résolution filesystem se fait via `scripts/pm_paths.py` (`PMConfig.path(...)`)
ou par défaut : `{projects_root}/clients/<entity>/projects/<project>/...`.

### Créer une entité (client / produit / self)
1. Copier `templates/client.md` dans `cfg.path("entity_client_dir", entity="<slug>")/overview.md`
2. Remplir les champs (slug, nom, type, contacts, defaults hérités)

### Créer un projet sous une entité existante
1. Copier `templates/project.md` dans `cfg.path("project_dir", entity="<C>", project="<P>")/overview.md`
2. Remplir les champs (slug, client, stack, intégrations, `redmine.project_id`)
3. Créer le dossier des tâches `cfg.path("tasks_dir", entity="<C>", project="<P>")`

### Créer une tâche
```bash
# Fetch automatique depuis Redmine (recommandé)
python3 scripts/redmine-fetch-task.py --issue 1234

# Le chemin de destination est résolu via pm.config.yml :: paths.task_file
```

### Nommage des fichiers
| Élément | Pattern (clé) | Format |
|---|---|---|
| Tâche | `paths.task_file` | `RM{id}_{titre-en-kebab-case}.md` |
| Journal | `paths.task_log_file` | `RM{id}_{titre-en-kebab-case}.log.md` |

## Structure du repo

```
project-management/                    # = pm.config.yml :: roots.pm_dir
  README.md                            # ce fichier
  Changelog.md                         # historique système
  PISTES.md                            # pistes d'évolution
  pm.config.yml                        # config des chemins (commitée)
  pm.config.local.yml                  # surcharge locale (gitignored, optionnel)
  .env                                 # credentials + PROJECTS_PATH (gitignored)
  .gitignore
  norms/
    NORMS.md                           # référence normative courante (v1.8.0)
    CHANGELOG.md                       # historique des évolutions du schéma
    archive/                           # snapshots des versions
  agents/
    worker-common.md                   # règles communes des workers
    worker-{role}.md                   # rôles spécifiques (dev, analyst, db, infra, design)
    orchestrateur.md
    reviewer.md
    summarizer.md
  scripts/
    pm_paths.py                        # lib résolution de chemins (PMConfig)
    validate-task.py
    priority.py                        # ordonnancement par ROI
    pm-dashboard.py                    # CLI dashboard
    redmine-fetch-task.py              # fetch Redmine → MD
    redmine-fetch-updates.py
    redmine-post-note.py
    pm-project-bootstrap.py
  templates/
    task.md                            # template tâche
    project.md                         # template projet
    client.md                          # template client
    aspects/                           # templates d'aspects (hosting, stack, environments…)
    bootstrap-tasks/                   # templates de tâches de bootstrap projet

# Repo séparé (chemin = $PROJECTS_PATH, défini dans .env)
$PROJECTS_PATH/                        # = pm.config.yml :: roots.projects_root
  clients/                             # = paths.entities_dir
    <entity>/                          # client | product | self
      client/                          # cahier des charges (overview + aspects)
      memory/                          # mémoire structurée
      projects/
        <project>/
          project/                     # cahier des charges projet
          memory/
          tasks/
            RM{id}_*.md                # = paths.task_file
            RM{id}_*.log.md            # = paths.task_log_file
          workspace                    # symlink → workspace de code
```

Côté workspace de code (ex: `/zfs/workspaces/<P>/`) : un symlink caché `.mmi-pm`
pointe vers le projet PM correspondant.

## Pour les agents IA

**Ordre de lecture au démarrage :** voir `CLAUDE.md` à la racine et `agents/worker-common.md`.

**Règle fondamentale :** Redmine est le mutex. L'assignation d'un ticket Redmine à un agent lui confère la propriété exclusive du fichier MD correspondant.

## Références

- Normes courantes : [norms/NORMS.md](norms/NORMS.md) (v1.8.0)
- Config des chemins : [pm.config.yml](pm.config.yml)
- Lib : [scripts/pm_paths.py](scripts/pm_paths.py)
- Redmine : défini globalement dans `.env`, surchargeable dans `project/overview.md`
- GitLab : https://gitlab.iprospective.fr
