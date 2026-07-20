---
name: mmi-pm-take
description: Prend un ticket en UN appel — statut en_cours + auto-assignation + env de session + branche <id>-<slug> + CF GIT, puis affiche le brief (≤ 30 lignes). Usage : "/mmi-pm-take 2364" ou langage naturel "prends RM2364", "je démarre RM2364". Ticket sans code : --no-branch.
allowed-tools: Bash, Read
---

# Skill : mmi-pm-take

Wrapper contextuel autour de `scripts/pm-task-take.py` (RM2364, CDC RM2316 § S3).
Encapsule la séquence canonique de prise d'un ticket — ne compose plus les
appels un à un, n'improvise pas l'ordre.

## Quand déclencher

- « prends / je prends / démarre / take RM<id> »
- `/mmi-pm-take <id> [--no-branch] [--repo PATH]`
- Invocation worker « traite la tâche RM<id> » : la prise en charge passe par ce skill.

## Invocation

```bash
scripts/pm-task-take.py <RM-id> [--no-branch] [--repo PATH] [--from BRANCHE]
```

- Idempotent : re-jouable sans dégât (statut déjà en_cours → skip, branche existante → checkout).
- Le brief final affiché EST le contexte de travail : ne pas relire le MD entier derrière.

## Gardes (rappel NORMS)

- **Jamais d'id prédit** : l'id vient de l'invocation ou de `pm-task-add --porcelain`, jamais « dernier vu + 1 » (tripwire #13).
- Ticket sans code (audit court, doc) : `--no-branch` — pas de branche ni d'infra inutile (flux court § S8).
- En cas d'échec d'une étape : le script indique l'étape et le script unitaire de reprise — ne pas re-dérouler à la main ce qui a réussi.
