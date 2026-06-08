---
name: mmi-pm-task-list
description: Liste les tâches d'un projet PM iProspective (lecture MD locale). Auto-détection du projet courant via le symlink `.mmi-pm` du workspace (ou cwd dans le repo PM). Support filtres status / type / priority / tag. Usage typique : "/mmi-pm-task-list" depuis un workspace, ou langage naturel "où en sont les tâches ?", "qu'est-ce qui reste à faire ?", "liste les tâches du projet".
allowed-tools: Bash, Read
---

# Skill : mmi-pm-task-list

Liste les tâches d'un projet PM (système iProspective de gestion `clients/<E>/projects/<P>/tasks/RM*.md`). Wrapper contextuel autour de `scripts/pm-task-list.py`.

## Quand le déclencher

- L'utilisateur demande "où en sont les tâches ?", "que reste-t-il à faire ?", "liste les tâches", "task list", "qu'y a-t-il en cours ?"
- L'utilisateur tape `/mmi-pm-task-list` (avec ou sans arguments)
- Tu es dans un workspace géré par PM et tu as besoin de connaître l'état des tâches avant d'agir

## Détection du contexte

Le script auto-détecte le projet courant dans cet ordre :

1. **`--project entity/project` explicite** (si fourni)
2. **Symlink `mmi-pm` ou `.mmi-pm`** dans `cwd` ou un ancêtre → suit → projet PM
3. **Position dans le repo PM** : si cwd est sous `<projects_root>/clients/<E>/projects/<P>/`
4. **Fallback** : liste de tous les projets

Tu n'as **pas** besoin d'interroger l'utilisateur sur le projet — le script s'en charge. Si le résultat est ambigu ("tous projets" alors qu'il en attend un seul), propose `--project <ent>/<proj>`.

## Comment l'invoquer

Le script est `<pm_dir>/scripts/pm-task-list.py`. Le repo PM est généralement `/zfs/workspaces/ai/project-management/`. Si tu n'es pas sûr, tente d'abord le path direct :

```bash
scripts/pm-task-list.py [options]
```

## Options principales

| Flag | Effet |
|---|---|
| `--project entity/project` | Cible explicite (sinon auto-détection) |
| `--status STATUS` | Filtre statut (répétable : `--status a_faire --status en_cours`) |
| `--not-status STATUS` | Exclut un statut (défaut : exclut `ferme` sauf si `--all` ou `--status` explicite) |
| `--type TYPE` | `bugfix`, `feature`, `assistance`, `maintenance`, `infrastructure`, etc. |
| `--priority PRIO` | `low`, `normal`, `high`, `urgent` |
| `--tag TAG` | Filtre par tag présent dans `tags[]` |
| `--include-closed` | Inclut les tâches fermées (sinon `ferme` exclu par défaut) |
| `--all` | Ignore l'auto-détection cwd → liste **TOUS** les projets |
| `--json` | Sortie JSON (pour pipe vers autre script) |

## Patterns d'usage typiques

```bash
# Tout le projet courant, statuts ouverts (défaut : exclut ferme)
./pm-task-list.py

# Vue globale, override auto-détection cwd
./pm-task-list.py --all

# Inclure les fermées du projet courant
./pm-task-list.py --include-closed

# Ce qui est en cours
./pm-task-list.py --status en_cours

# Tâches urgentes ou hautes du projet courant
./pm-task-list.py --priority urgent --priority high

# Bootstrap tasks restantes
./pm-task-list.py --tag bootstrap --status a_faire

# Pour scripting
./pm-task-list.py --json | jq '.[] | select(.priority=="urgent")'
```

## Conventions de statut PM

Ordre logique (le script trie en priorité par statut) :
- `en_cours` (en train d'être travaillée)
- `a_corriger` (revue, à reprendre)
- `a_tester_verifier` (à valider)
- `a_faire` (prêt à démarrer)
- `etude_chiffrage_en_cours` / `a_etudier_chiffrer` (en amont)
- `ferme` (clos)

Détails dans `<pm_dir>/norms/NORMS.md`.

## Sortie attendue

Table avec colonnes : `RM<id>` · `Projet` (si scope global) · `Statut` · `Priorité` · `Type` · `Titre`.

Quand tu présentes la sortie à l'utilisateur, **ne re-paraphrase pas la table** entière — résume ce qui ressort (nombre de tâches, urgences, ce qui est bloquant). Mentionne l'ID exact `RMnnnn` quand tu réfères à une tâche pour qu'il puisse cliquer.

## Limites connues v1

- **MD-only** : si le statut MD n'est pas sync avec Redmine, l'affichage est périmé. Ne pas s'en servir comme source de vérité "officielle" — c'est ce que sait le repo PM. Pour rafraîchir, voir `scripts/redmine-fetch-updates.py` (séparé).
- Pas de filtre `assignee` / `team` (les frontmatters n'ont pas toujours d'assignee).
- Pas de filtre par date (`updated_since`, `due_before`) — à ajouter si besoin émerge.
