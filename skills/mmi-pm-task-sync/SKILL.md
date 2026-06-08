---
name: mmi-pm-task-sync
description: Synchronise une tâche MD locale avec son état actuel Redmine. Sync les champs frontmatter (status, priority, title, due, updated) ET appende les nouveaux journaux au .log.md. Combinaison de redmine-fetch-updates.py (qui ne syncait que les journaux) et de la mise à jour des champs frontmatter. Utile quand qqn change le statut/priorité côté Redmine UI ou via un autre agent — sans cela, le MD reste périmé sur ces champs. Usage : "/mmi-pm-task-sync 1234" ou langage naturel "synchronise RM1234", "rafraîchis la tâche 1234 depuis Redmine".
allowed-tools: Bash, Read
---

# Skill : mmi-pm-task-sync

Wrapper contextuel autour de `scripts/pm-task-sync.py`.

## Quand déclencher

- "synchronise RM<id>", "sync RM<id>", "refresh RM<id>"
- "rafraîchis la tâche <id> depuis Redmine"
- "rapatrie les modifs Redmine pour RM<id>"
- Tu détectes une discordance entre MD local et Redmine (status, priorité)
- `/mmi-pm-task-sync <id>` ou `/mmi-pm-task-sync --all-tasks`

## Invocation

```bash
scripts/pm-task-sync.py <RM-id> [--dry-run] [--no-journals]
```

## Exemples

```bash
# Sync simple : champs frontmatter + journaux
./pm-task-sync.py 1669

# Voir les diffs sans appliquer
./pm-task-sync.py 1669 --dry-run

# Sync les champs seulement (skip les notes)
./pm-task-sync.py 1669 --no-journals

# Sync TOUTES les tâches (attention : 1 appel API par tâche)
./pm-task-sync.py --all-tasks --dry-run    # voir d'abord
./pm-task-sync.py --all-tasks              # pour de vrai
```

## Champs synchronisés

| Champ Redmine | Champ MD frontmatter |
|---|---|
| `subject` | `title` |
| `status.id` | `status` (mapping NORMS) |
| `priority.id` | `priority` (low/normal/high/urgent) |
| `due_date` | `due` |
| `updated_on` | `updated` |
| `journals[]` (nouveaux) | append au `.log.md` |

Mapping `status_id` → NORMS :
- 8 → `a_etudier_chiffrer`
- 14 → `etude_chiffrage_en_cours`
- 12 → `a_faire`
- 2 → `en_cours`
- 9 → `a_tester_verifier`
- 11 → `a_corriger`
- 5 → `ferme` + close_reason `resolu`
- 10 → `ferme` + close_reason `abandonne`
- 6 → `ferme` + close_reason `wont_fix` (ou `hors_perimetre` — ambigu, à raffiner manuellement)
- 7 → `ferme` + close_reason `invalide` (ou `doublon` — ambigu)

## Notes

- **Sens unique** : Redmine → MD (pas MD → Redmine). Pour pousser un changement MD vers Redmine, utiliser `mmi-pm-task-status-update` ou `mmi-pm-task-comment`.
- Si la tâche n'a **pas** encore de MD local, utiliser plutôt `redmine-fetch-task.py` pour faire l'import initial.
- Différence avec `redmine-fetch-updates.py` (ancien script) : celui-là synchronise aussi les **champs frontmatter**, pas seulement le pointeur de journal et le log.
- Utilise `REDMINE_USER_MAIN_API_KEY` (Karl, compte central) par défaut.
