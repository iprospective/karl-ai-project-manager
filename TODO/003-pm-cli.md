# TODO 003 — CLI projet `pm` (commandes depuis le workspace projet)

| | |
|---|---|
| **Statut** | `pending` |
| **Priorité** | `#priority:high` |
| **Tags** | `#user-request` `#redmine` `#gitlab` `#agents` |
| **Origine** | Demande user — 2026-05-12 |
| **Créé** | 2026-05-12 |

## Contexte

La convention de stockage v1.5.0 (puis v1.8.0 — symlink renommé `.mmi-pm` caché) met
un symlink dans chaque workspace projet, pointant vers le dossier PM centralisé. Un
outil CLI `pm` exécuté depuis le workspace projet permet d'orchestrer les opérations
courantes (création de ticket Redmine + fichier MD + commit) sans naviguer entre les
arbres.

## Commandes prévues

### Création
- [ ] `pm task create --type <T> --title "..."`
  - Crée le ticket Redmine dans le projet configuré (`.mmi-pm/project/overview.md ::
    redmine.project_id`)
  - Récupère l'ID
  - Génère `.mmi-pm/tasks/RM{id}_{slug}.md` depuis `templates/task.md`
  - Commit + push dans le repo `ai-projects`
- [ ] `pm project init <client-slug> <project-slug>`
  - Crée le squelette PM centralisé via `cfg.path("project", entity=<C>, project=<P>)`
  - Crée le symlink `paths.reverse_link` (`.mmi-pm`) dans le workspace courant et
    le symlink `paths.workspace_link` (côté PM)
  - Initialise `project/overview.md` depuis le template
- [ ] `pm client init <client-slug>`
  - Crée le squelette client centralisé

### Lecture
- [ ] `pm task list` — top ROI du projet courant (utilise `scripts/priority.py`)
- [ ] `pm task show <RM{id}>` — affiche la tâche (frontmatter + body + 50 dernières lignes de log)
- [ ] `pm status` — vue d'ensemble du projet courant (counts par statut)

### Workflow
- [ ] `pm task assign <RM{id}> <agent>` — assignation via API Redmine
- [ ] `pm task close <RM{id}> --reason <resolu|...>` — passage en `ferme`

## Implémentation

- Python, packagé en single-file ou `setup.py` standard
- Utilise `scripts/pm_paths.py` (`PMConfig.load()`) pour tous les chemins ; lit
  `$REDMINE_URL`/`$REDMINE_API_KEY` depuis `.env`
- Résolution du contexte projet : `realpath .mmi-pm` → tree central
- Validator appelé avant tout commit

## Critères d'acceptation

- Cycle complet utilisable : `pm project init` → `pm task create` → `pm task assign` → `pm task close`
- Toute tâche créée passe `scripts/validate-task.py`
- Un test E2E couvre le cycle de vie complet (peut être basé sur une instance Redmine de test)

## Journal

- **2026-05-12** : TODO créée. Workflow CLI → Redmine + MD acté en v1.5.0 (cf NORMS § Lien Redmine ↔ MD). Reste à implémenter.
