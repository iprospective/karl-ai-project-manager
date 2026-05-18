# TODO 007 — Flatten `projects/clients/` → `projects/`

| | |
|---|---|
| **Statut** | `pending` |
| **Priorité** | `#priority:normal` |
| **Tags** | `#user-request` `#structure` `#norms` |
| **Origine** | Réflexion architecture — 2026-05-15 (suite à la discussion sur la couche d'abstraction `pm.config.yml` v1.8.0) |
| **Créé** | 2026-05-15 |
| **Ticket Redmine** | [#1668](https://tasks.iprospective.fr/issues/1668) (projet `ai-agents` = "Gestion de projet pour agents IA") |

## Contexte

Le sous-repo `projects/` ne contient aujourd'hui qu'**un seul dossier utile** :
`clients/`. La structure résultante a `projects/clients/<entity>/projects/<project>/`
— le mot "projects" apparaît trois fois dans un chemin de tâche.

L'étape A (`pm.config.yml` + `scripts/pm_paths.py`) a été livrée en v1.8.0 et
abstrait tous les chemins. L'étape B (ce TODO) consiste à supprimer le niveau
`clients/` superflu.

**Décision actée** : le flatten est pertinent. Reporté pour grouper avec un autre
bump NORMS plutôt que le faire isolément.

## Changements à effectuer

### 1. Modifier `pm.config.yml`

Une seule clé à changer :
```yaml
# Avant
entities_dir: "{projects_root}/clients"

# Après
entities_dir: "{projects_root}"
```

Toutes les autres clés (`entity`, `entity_projects_dir`, `project`, `tasks_dir`,
`task_file`, etc.) se résolvent par cascade depuis `entities_dir` — rien d'autre
à toucher dans la config.

### 2. Déplacer les dossiers (sous-repo `projects/`)

```bash
cd "$PROJECTS_PATH"
git mv clients/* .
rmdir clients
```

État après : `projects/iprospective/`, `projects/redmine/`, `projects/lemathou/`,
`projects/nextcloud/` (si encore présent au moment du flatten).

### 3. Régénérer les symlinks `.mmi-pm` côté workspaces

Les symlinks pointent vers `projects/clients/<C>/projects/<P>/`. Après flatten :
```bash
# Pour chaque workspace ayant un .mmi-pm
for ws in /zfs/workspaces/redmine /zfs/workspaces/perso/mathematicians-db; do
  cible=$(readlink "$ws/.mmi-pm")
  nouvelle=$(echo "$cible" | sed 's|/projects/clients/|/projects/|')
  rm "$ws/.mmi-pm"
  ln -s "$nouvelle" "$ws/.mmi-pm"
done
```

Un futur `pm sync-links` (cf. TODO/003) régénérera tous les symlinks à partir
de la config, ce qui simplifierait ce point.

### 4. Bump NORMS

- `norms/NORMS.md` : section "Repo projets" — supprimer le niveau `clients/`
  dans l'arborescence. Bump v1.8.0 → v1.9.0 (mineur — structure observable change).
- Archive de la v1.8.0 dans `norms/archive/NORMS_v1.8.0.md`
- `norms/CHANGELOG.md` + `Changelog.md` racine : entrée v1.9.0

### 5. Mettre à jour les exemples « par défaut » dans la doc

Quelques endroits mentionnent la résolution par défaut comme
`{projects_root}/clients/<C>/projects/<P>/` pour aider à la lecture humaine.
À mettre à jour vers `{projects_root}/<C>/projects/<P>/`.

Fichiers concernés (à regrep le jour J) :
- `norms/NORMS.md` (1-2 mentions « par défaut »)
- `README.md`
- `agents/worker-common.md`
- `pm.config.yml` (commentaire d'entête)

## Critères d'acceptation

- [ ] `pm.config.yml :: paths.entities_dir` ne contient plus `/clients`
- [ ] `projects/clients/` n'existe plus côté sous-repo `projects/`
- [ ] Les 2+ symlinks `.mmi-pm` existants pointent vers les nouveaux paths
- [ ] `python3 scripts/pm-dashboard.py` liste correctement entités/projets/tâches
- [ ] `python3 scripts/redmine-fetch-task.py --issue <id> --dry-run` résout
      correctement la destination
- [ ] `python3 scripts/redmine-fetch-updates.py --issue <id> --dry-run` trouve
      le MD
- [ ] Aucun script ne plante, aucune tâche existante n'est cassée
- [ ] NORMS v1.9.0 livré + archive v1.8.0
- [ ] Commit unique côté repo PM + commit unique côté sous-repo `projects/`

## Dépendances

- **Bloque** : aucune dépendance bloquante côté code (la lib `pm_paths` rend ça
  trivial).
- **Bloqué par** : création du projet PM côté arbo
  (`clients/iprospective/projects/pm-ai-agents/` aligné avec
  `redmine.project_id: pm-ai-agents`) — **fait le 2026-05-15** (cf. journal).
- **Co-bénéfice** : un futur `pm sync-links` simplifierait l'étape 3 et
  pourrait être livré en même temps (cf. TODO/003).

## Journal

- **2026-05-15** : TODO créée. Étape A (`pm.config.yml` + `pm_paths.py`) livrée
  en commit `40fc7b5` (NORMS v1.8.0). Étape B reportée — pas urgente, à grouper
  avec un autre bump NORMS pour limiter les ruptures.
- **2026-05-15** : Projet Redmine `ai-agents` (id=66) renommé "Gestion de
  projet pour agents IA" (name uniquement — l'identifier `ai-agents` n'est
  pas modifiable via API). Ticket [#1668](https://tasks.iprospective.fr/issues/1668)
  créé pour cette tâche.
- **2026-05-15 (suite)** : 2e renommage du projet id=66 → name "PM — Agents IA
  & Outils PM", identifier `pm-ai-agents` (forcé en SQL direct via mmi, car
  l'API Redmine refuse la modif d'identifier). Création du projet PM côté arbo
  `clients/iprospective/projects/pm-ai-agents/` (workspace = le repo PM
  lui-même, dogfooding). Memberships par défaut déjà présents.
