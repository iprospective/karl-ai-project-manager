---
name: mmi-pm-task-status-update
description: Change le statut d'une tâche : sync Redmine (PUT + note auto) + sync MD (frontmatter `status`, append `status_history`, refresh `updated`) + append log. Statuts NORMS : nouveau, a_etudier_chiffrer, etude_chiffrage_en_cours, etude_chiffrage_a_valider, a_faire, en_cours, a_tester_dev, a_tester_demandeur, a_mep, en_mep, en_pause, a_corriger, ferme. Réattribution auto au demandeur sur etude_chiffrage_a_valider et a_tester_demandeur. Usage : "/mmi-pm-task-status-update 1669 en_cours" ou langage naturel "passe RM1669 en cours", "soumets l'étude de RM1234 à validation", "ferme RM1234 résolu".
allowed-tools: Bash, Read, AskUserQuestion
---

# Skill : mmi-pm-task-status-update

Wrapper contextuel autour de `scripts/pm-task-status-update.py`. Suit la convention `mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

## Quand déclencher

- "passe RM<id> <status>", "RM<id> est en cours"
- "ferme RM<id>", "clôture RM<id> résolu"
- "RM<id> à tester"
- `/mmi-pm-task-status-update <id> <status>`

## Détection contexte

Détection du projet courant via `cwd` (symlink `mmi-pm` ou `.mmi-pm` ou position dans `<projects_root>/clients/<E>/projects/<P>/`). Pas besoin de demander à l'utilisateur si le contexte est résolvable.

## Invocation

```bash
scripts/pm-task-status-update.py <RM-id> <new-status> [--close-reason X] [--note "..."]
```

## Exemples

```bash
# Passer en_cours
./pm-task-status-update.py 1669 en_cours

# Fin de la phase d'étude : soumettre le CDC/chiffrage au demandeur (auto-réassigne à l'author)
./pm-task-status-update.py 1669 etude_chiffrage_a_valider --note "CDC + chiffrage finis, à valider"

# Passer a_tester_demandeur (auto-réassigne au demandeur côté Redmine)
./pm-task-status-update.py 1669 a_tester_demandeur --note "Livré en commit abcd"

# Fermer (close_reason obligatoire)
./pm-task-status-update.py 1669 ferme --close-reason resolu --note "OK"
./pm-task-status-update.py 1669 ferme --close-reason wont_fix
```

## Notes

close_reason valides : resolu, abandonne, wont_fix, hors_perimetre, invalide, doublon. La règle NORMS (a_tester_verifier → réassignation à l'auteur) est appliquée par `redmine-post-note.py` sous-jacent.
