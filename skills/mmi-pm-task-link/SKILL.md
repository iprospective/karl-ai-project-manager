---
name: mmi-pm-task-link
description: Crée, liste ou supprime un lien entre tâches PM (frontmatter + relation Redmine + log). Types supportés (NORMS v1.9.0) — `relates` (latéral non-bloquant), `depends_on` (A attend B), `blocks` (A bloque B). Le miroir est maintenu automatiquement côté cible. Usage : "/mmi-pm-task-link add 1708 1703 --type relates", ou langage naturel "lie RM1708 et RM1703", "liste les relations de RM1234", "délie RM1234 et RM5678".
allowed-tools: Bash, Read, AskUserQuestion
---

# Skill : mmi-pm-task-link

Wrapper contextuel autour de `scripts/pm-task-link.py`. Suit la convention `mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

## Quand déclencher

- "lie RM<X> et RM<Y>", "relie RM<X> à RM<Y>"
- "RM<X> dépend de RM<Y>", "RM<X> bloque RM<Y>"
- "liste les relations de RM<id>", "quels liens pour RM<id> ?"
- "délie RM<X> et RM<Y>", "supprime le lien entre RM<X> et RM<Y>"
- "synchronise les liens de RM<id> depuis Redmine"
- `/mmi-pm-task-link <sub-cmd> ...`

## Désambiguïsation du type

Si l'utilisateur ne précise pas le type, **demander** via `AskUserQuestion` ou inférer du verbe :

| Verbe utilisateur | Type |
|---|---|
| "lie", "relie", "même sujet", "famille" | `relates` |
| "dépend de", "attend", "bloqué par" | `depends_on` |
| "bloque", "doit finir avant" | `blocks` |

`relates` est la valeur par défaut du script si non précisée.

## Invocation

```bash
scripts/pm-task-link.py add  <from> <to> --type {relates|depends_on|blocks}
scripts/pm-task-link.py list <id>
scripts/pm-task-link.py rm   <from> <to> [--type T]
scripts/pm-task-link.py sync <id>
```

## Exemples

```bash
# Lien latéral (même sujet)
./pm-task-link.py add 1708 1703 --type relates

# Dépendance bloquante
./pm-task-link.py add 1234 1230 --type depends_on        # 1234 attend 1230

# Liste les liens (frontmatter + relations Redmine, signale les drifts)
./pm-task-link.py list 1709

# Sync depuis Redmine (utile après création manuelle d'une relation côté Redmine)
./pm-task-link.py sync 1708

# Supprimer un lien (les deux côtés + relation Redmine)
./pm-task-link.py rm 1708 1703
```

## Effets

- Maintient le **frontmatter** des deux tâches (champ + miroir côté cible)
- Maintient la **relation Redmine** (POST/DELETE)
- Append une entrée dans chaque `.log.md` ("Lien (pm-task-link)")
- Met à jour `updated` côté frontmatter

## Notes

- Le script ne gère pas `parent_task`/`sub_tasks` — c'est un attribut Redmine (`parent_issue_id`), pas une relation. À traiter dans un autre outil si besoin.
- Le champ `refs` reste manuel (référence libre, pas de relation Redmine).
- Sens des dépendances : `A.depends_on = [B]` veut dire "A attend B" ; côté Redmine ça se traduit par une seule relation `blocks` postée depuis B.
