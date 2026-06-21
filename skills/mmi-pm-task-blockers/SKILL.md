---
name: mmi-pm-task-blockers
description: Explique POURQUOI un ticket ne peut pas changer de statut / être fermé. Liste les relations bloquantes ouvertes (blocks/precedes = NORMS depends_on) ET les sous-tâches ouvertes, et dit quoi clôturer d'abord. À lancer dès qu'une transition (surtout vers `ferme`) est refusée silencieusement, AVANT de conclure à un problème de droits/rôle/workflow. Usage : "/mmi-pm-task-blockers 1813", "pourquoi RM1813 ne se ferme pas ?", "qu'est-ce qui bloque RM1813 ?".
allowed-tools: Bash
---

# Skill : mmi-pm-task-blockers

Wrapper contextuel autour de `scripts/pm-task-blockers.py`. Suit la convention
`mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

Répond à « pourquoi RM\<id\> ne change pas de statut / ne se ferme pas ? » sans
spéculer : Redmine refuse **silencieusement** (PUT 204, `status_id` ignoré) une
fermeture tant qu'un **bloqueur** reste ouvert. Les deux causes réelles :
- une **relation bloquante** (`blocks` / `precedes` = NORMS `depends_on`) dont le
  ticket source est encore ouvert ;
- une **sous-tâche** ouverte.

⚠️ Ce n'est **ni** un problème de droits, **ni** de rôle, **ni** de tracker
(« Évolution » et « Tâche » ont les mêmes droits — cf. NORMS `status-workflow`,
§ *Préconditions de fermeture*).

## Quand déclencher

- "pourquoi RM\<id\> ne se ferme pas ?", "qu'est-ce qui bloque RM\<id\> ?"
- réflexe **systématique** quand `pm-task-status-update <id> ferme` rapporte
  « statut PAS changé » / un refus silencieux
- `/mmi-pm-task-blockers <id>`

## Invocation

```bash
scripts/pm-task-blockers.py <RM-id>          # rapport lisible (exit 2 si bloqué)
scripts/pm-task-blockers.py <RM-id> --json   # pour l'outillage
```

## Comportement de l'agent

- Lancer le script et **relayer le verdict** : les bloqueurs ouverts + « clôture
  d'abord #… ».
- S'il faut débloquer : traiter/fermer les bloqueurs listés (récursif si eux-mêmes
  bloqués), puis re-tenter la transition.
- Ne **jamais** conclure à un problème de droits/workflow avant d'avoir lancé ce check.
