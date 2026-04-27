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
# Éditer .env avec les vraies valeurs (GitLab token, Redmine API key...)

# 3. Cloner le repo des projets dans projects/
git clone git@gitlab.iprospective.fr:iprospective/ai-projects.git projects/
```

## Démarrage rapide

### Créer un projet
1. Copier `templates/project.md` dans `projects/{nom-projet}/project.md`
2. Remplir les champs (nom, Redmine, GitLab, équipe)
3. Créer le dossier `projects/{nom-projet}/tasks/`

### Créer une tâche
1. Ouvrir le ticket Redmine correspondant, noter l'ID
2. Copier `templates/task.md` dans `projects/{nom-projet}/tasks/RM{id}_{titre-kebab}.md`
3. Remplir le frontmatter (redmine_id, title, type, priority, due...)
4. Rédiger les sections Contexte, Critères d'acceptation, Instructions
5. Créer le fichier journal vide : `RM{id}_{titre-kebab}.log.md`

### Nommage des fichiers
| Élément | Format |
|---|---|
| Tâche | `RM{id}_{titre-en-kebab-case}.md` |
| Journal | `RM{id}_{titre-en-kebab-case}.log.md` |

## Structure du repo

```
project-management/
  README.md                   # ce fichier
  CHANGELOG.md                # historique système
  .gitignore
  norms/
    NORMS.md                  # référence normative courante (v1.1)
    CHANGELOG.md              # historique des évolutions du schéma
    archive/                  # snapshots des versions majeures
  projects/
    {nom-projet}/
      project.md
      tasks/
        RM{id}_{titre}.md
        RM{id}_{titre}.log.md
  templates/
    task.md                   # template tâche complet
    project.md                # template projet
  agents/
    orchestrateur.md          # rôle et protocole de l'orchestrateur
    worker-dev.md             # worker feature / bugfix / refactoring
    worker-analyst.md         # worker audit / research / documentation
    reviewer.md               # agent de validation
```

## Pour les agents IA

**Ordre de lecture au démarrage :**
1. [`norms/NORMS.md`](norms/NORMS.md) — schéma, règles, machine d'états, protocoles
2. [`agents/{votre-rôle}.md`](agents/) — instructions spécifiques à votre rôle
3. `projects/{projet}/project.md` — contexte du projet en cours
4. `projects/{projet}/tasks/RM{id}_*.md` — tâche(s) assignée(s)

**Règle fondamentale :** Redmine est le mutex. L'assignation d'un ticket Redmine à un agent lui confère la propriété exclusive du fichier MD correspondant.

## Références

- Normes courantes : [norms/NORMS.md](norms/NORMS.md) `schema_version: 1.1`
- Redmine : défini par projet dans `project.md`
- GitLab : https://gitlab.iprospective.fr
