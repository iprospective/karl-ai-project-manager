---
name: mmi-pm-task-comment
description: Poste une note sur un ticket Redmine ET append l'entrée correspondante au `.log.md` local. Wrapper autour de `redmine-post-note.py`. Usage : "/mmi-pm-task-comment 1669 --note '...'" ou langage naturel "commente RM1669 : ...", "ajoute une note à 1234".
allowed-tools: Bash, Read, AskUserQuestion
---

# Skill : mmi-pm-task-comment

Wrapper contextuel autour de `scripts/pm-task-comment.py`. Suit la convention `mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

## Quand déclencher

- "commente RM<id> : ...", "ajoute une note à RM<id>"
- "poste sur RM<id> : ..."
- `/mmi-pm-task-comment <id> --note "..."`

## Détection contexte

Détection du projet courant via `cwd` (symlink `mmi-pm` ou `.mmi-pm` ou position dans `<projects_root>/clients/<E>/projects/<P>/`). Pas besoin de demander à l'utilisateur si le contexte est résolvable.

## Invocation

```bash
scripts/pm-task-comment.py <RM-id> --note "texte" [--private]
```

## Exemples

```bash
# Note simple
./pm-task-comment.py 1669 --note "Bloqué sur la décision conflit policy"

# Note multilignes via stdin
echo -e 'Avancement :\n- A fait X\n- Reste Y' | ./pm-task-comment.py 1669 --note -

# Note privée (non visible client)
./pm-task-comment.py 1669 --note "Note interne" --private
```

## Notes

La note est postée Redmine + appendée au `.log.md` local. Si tu veux **aussi** changer le statut, utilise plutôt `mmi-pm-task-status-update` qui inclut une note.
