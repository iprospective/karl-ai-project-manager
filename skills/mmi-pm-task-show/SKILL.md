---
name: mmi-pm-task-show
description: Affiche les détails d'une tâche PM (MD frontmatter + corps + tail du log + optionnel: refresh Redmine). Trouve automatiquement le fichier par son RM-id parmi tous les projets PM. Usage : "/mmi-pm-task-show 1669" ou langage naturel "montre RM1669", "détails de la tâche 1234", "ouvre RM1234".
allowed-tools: Bash, Read, AskUserQuestion
---

# Skill : mmi-pm-task-show

Wrapper contextuel autour de `scripts/pm-task-show.py`. Suit la convention `mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

## Quand déclencher

- "montre RM<id>", "ouvre la tâche RM<id>", "détails RM<id>"
- "que dit RM<id> ?", "qu'est-ce que la tâche 1234 ?"
- Utilisateur tape `/mmi-pm-task-show <id>`

## Détection contexte

Détection du projet courant via `cwd` (symlink `mmi-pm` ou `.mmi-pm` ou position dans `<projects_root>/clients/<E>/projects/<P>/`). Pas besoin de demander à l'utilisateur si le contexte est résolvable.

## Invocation

```bash
scripts/pm-task-show.py <RM-id> [--log-lines N] [--fetch-redmine]
```

## Exemples

```bash
# Afficher RM1669 + dernières 30 lignes de log
./pm-task-show.py 1669

# Avec plus de contexte log
./pm-task-show.py 1669 --log-lines 100

# Rafraîchir aussi depuis Redmine (dernier journal)
./pm-task-show.py 1669 --fetch-redmine
```

## Notes

Le script utilise `PMConfig.find_task(rm_id)` qui scanne tous les projets — aucun besoin de spécifier l'entité/projet. Si l'utilisateur veut juste le contenu de la tâche, pas le log, lire le fichier directement avec Read.
