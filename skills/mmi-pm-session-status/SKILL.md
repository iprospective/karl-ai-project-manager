---
name: mmi-pm-session-status
description: Suivi d'avancement par session — enregistre au fil de l'eau les tickets/tâches ouverts dans la session et leur statut, et répond cheap (lecture d'un seul fichier, sans rescanner le contexte) à « il reste quoi à faire dans cette session » / « où en est-on » / « récap session ». Usage : "/mmi-pm-session-status", ou langage naturel "il reste quoi à faire ?", "récap de la session", "qu'est-ce qu'on a ouvert comme tickets ?".
allowed-tools: Bash
---

# Skill : mmi-pm-session-status

Wrapper contextuel autour de `scripts/pm-session-status.py`. Suit la convention
`mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

Maintient un **worklog par session Claude Code** (keyé par `$CLAUDE_CODE_SESSION_ID`) listant
les tickets/tâches touchés dans la session et leur avancement. Permet de répondre à
« il reste quoi à faire ? » en **lisant un seul petit fichier** — pas de re-scan du contexte,
donc peu de tokens, et ça survit à la compaction.

Implémente le volet « manifest déclaratif » de **RM1875** (NORMS — suivi par session).

## Stockage (instance-local, jamais committé)

- Source de vérité : `~/.claude/session-worklogs/<session-id>.json`
- Rendu lisible (régénéré à chaque mutation) : `~/.claude/session-worklogs/<session-id>.md`

État de session éphémère et propre à l'instance → **hors repo PM** (ne pas committer).

## Quand déclencher

**Lecture** (la question cible) :
- "il reste quoi à faire (dans cette session) ?", "où en est-on ?", "récap session",
  "qu'est-ce qu'on a ouvert ?", "/mmi-pm-session-status" → `show`

**Écriture** (à faire PROACTIVEMENT par l'agent, sans que l'utilisateur le demande) :
- dès qu'un **ticket PM est créé** dans la session → `add RM<id> "<libellé>" --project <p> --status nouveau`
- dès qu'une **tâche/chantier non-ticket** est décidé (« reste le déploiement prod ») → `add <slug> "<libellé>" --status à_faire`
- dès qu'un item **change d'état** (fait, en attente, bloqué) → `set <ref> <statut>`

## Invocation

```bash
# (depuis la racine du repo PM)
scripts/pm-session-status.py show          # afficher l'état (défaut)

# ajouter / upsert un item (ref = RM-id ou slug libre)
scripts/pm-session-status.py add RM1886 "Git-hooks par environnement" --project pm-ai-agents --status nouveau
scripts/pm-session-status.py add pisceen-facettes "Fix #-serveur facettes" --status en_attente --note "uncommitted; reste test nav + commit + déploiement prod"

# changer un statut / divers
scripts/pm-session-status.py set RM1886 en_cours
scripts/pm-session-status.py rm <ref>
scripts/pm-session-status.py title "Libellé de la session"
```

## Statuts

Texte libre, mais reconnus pour le tri d'affichage :
- **terminés** (sortis du « reste à faire ») : `fait`, `done`, `ferme`, `livré`, `résolu`, `closed`
- **en attente / bloqué** (section à part) : `en_attente`, `bloqué`, `waiting`, `a_valider`
- tout le reste (`à_faire`, `en_cours`, `nouveau`, …) → **Reste à faire**

Pour les tickets PM, garder une cohérence avec les statuts NORMS quand pertinent
(`nouveau`, `en_cours`, `a_tester_demandeur`, `a_mep`, `ferme`…).

## Comportement de l'agent

- Sur une question « reste quoi à faire / récap » → exécuter `show` et **relayer la sortie** (déjà lisible en Markdown).
- Au fil de la session → **logger les créations/changements** de tickets et chantiers (voir « Écriture »), pour que `show` reste fidèle.
- Le worklog est **par session** : ne reflète que ce que CETTE session a ouvert/touché, pas l'ensemble du backlog projet (pour ça → `mmi-pm-task-list`).
