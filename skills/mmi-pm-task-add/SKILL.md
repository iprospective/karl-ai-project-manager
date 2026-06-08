---
name: mmi-pm-task-add
description: Crée une nouvelle tâche : POST Redmine + génère MD + log + valide. Auto-détection du projet via cwd (symlink `.mmi-pm` ou position dans repo PM). Slug auto depuis title. Usage : "/mmi-pm-task-add --title 'Setup CI' --type infrastructure --priority high" ou langage naturel "ajoute une tâche 'X' dans le projet courant".
allowed-tools: Bash, Read, AskUserQuestion
---

# Skill : mmi-pm-task-add

Wrapper contextuel autour de `scripts/pm-task-add.py`. Suit la convention `mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

## Quand déclencher

- "crée une tâche : ...", "ajoute une tâche : ..."
- "new task ..."
- `/mmi-pm-task-add --title "..."`

## Détection contexte

Détection du projet courant via `cwd` (symlink `.mmi-pm` ou position dans `<projects_root>/clients/<E>/projects/<P>/`). Pas besoin de demander à l'utilisateur si le contexte est résolvable.

## Invocation

```bash
scripts/pm-task-add.py --title "..." [--type T] [--priority P] [--description "..."] [--tags csv]
```

## Exemples

```bash
# Depuis un workspace (auto-detect projet)
./pm-task-add.py --title "Setup CI GitLab" --type infrastructure --priority high

# Avec description et tags
./pm-task-add.py --title "Corriger bug X" --type bugfix --priority high \
  --description "Détails du bug..." --tags "bug,urgent"

# Override projet
./pm-task-add.py --project iprospective/pm-ai-agents --title "..." --type feature
```

## Notes

Types : bugfix, feature, assistance, infrastructure, maintenance, autre. Priorities : low, normal, high, urgent. Mapping vers Redmine tracker/priority géré automatiquement.
