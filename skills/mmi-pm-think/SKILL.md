---
name: mmi-pm-think
description: Consigne la réflexion d'un ticket dans son fichier frère `RM<id>_<slug>.think.md` (notes verbatim N, questions Q, décisions/conseils D/C, fonctionnalités F, états ✅ ❌ 🟡 🕐 ⏸) et la fusionne vers les fichiers du projet (`docs/cdc-questions.md`, `cdc-decisions.md`, `cdc-features.md`, `cdc-notes.md`). Usage : "/mmi-pm-think 3015 --decide '…'", ou langage naturel "consigne la décision sur RM3015", "note cette question dans le ticket", "qu'est-ce qui reste ouvert sur RM3015 ?", "fusionne les think du projet".
allowed-tools: Bash, Read
---

# Skill : mmi-pm-think

Wrapper contextuel autour de `scripts/pm-task-think.py` et `scripts/pm-think-merge.py` (RM3015, RM3053).
Règle NORMS : `session-tooling` § « Consignation par ticket — le `.think.md` ».

## Quand déclencher

- Un **conseil** rendu, un **arbitrage** du demandeur, une **question** laissée ouverte, une
  **fonctionnalité** qui prend forme → **dans le même tour** que la discussion.
- « qu'est-ce qui reste ouvert / décidé sur RM<id> ? » → `--show`.
- Avant de livrer ou de fermer : `pm-think-merge --check` (et la garde de clôture refuse les Q ouvertes).
- `/mmi-pm-think <id> --note|--question|--decide|--advise|--feature "…"`.

## Quoi consigner — et quoi ne PAS consigner (RM3062)

- **N note** : seulement **ce qui n'a pas été traité** et pourra servir — un report (« pour l'instant…
  on verra plus tard »), un manque, une intention différée ; il faut qu'on comprenne QUOI reste à faire
  en lisant la note seule. **Jamais** une demande d'exécution (même longue), une réponse à une question
  (c'est une D), une contrainte (c'est une D), un bug (c'est un ticket), un accord, un collage.
  Une dette retenue se **reformule aussitôt** en Q ou F : le vrac est un sas.
- **D décision** : ce que le demandeur **demande de faire, pose ou tranche** — réponse à une
  question ou non, ticketé ou non. **C** : le conseil de l'agent, 🟡 jusqu'à l'arbitrage.
- **F fonctionnalité** : une feature **atomique** qui donne lieu à un ticket, le complète, ou
  reste à faire plus tard.
- **Q question** : ce qui n'est pas tranché, ce que ça bloque, l'urgence, l'avis.
- **Signature** : `--by M` = le demandeur nommé (`PM_THINK_HUMAN`, sinon le manager IA de la conf), `--by A` (défaut) = le
  modèle de la session (`PM_THINK_AUTHOR`, sinon le transcript), ou un nom explicite (`--by Paul`). Les propositions de
  l'IA sont moissonnées en notes signées du modèle. Élagage : `pm-think-harvest --prune --all [--delete]`.

## Ce que les scripts font déjà (ne pas doublonner)

- Le hook `pm-think-harvest` (Stop / SessionEnd) consigne **tout seul** les questions posées
  (`AskUserQuestion`, `ExitPlanMode`), les réponses retenues (→ D ✅) et les demandes verbatim
  du demandeur (→ N). `pm-session-status request --ticket RM<id>` et `notify --ref RM<id>`
  descendent aussi dans le think.
- L'agent n'écrit donc à la main que ce qu'aucun script ne peut inférer : le **conseil**
  (options, pour/contre, motif) et l'**arbitrage** quand il n'est pas passé par une question outillée.

## Invocation

```bash
scripts/pm-task-think.py <id> --advise "…"                      # C, 🟡 (conseil de l'agent)
scripts/pm-task-think.py <id> --decide "…" --state valide --by M # D ✅ (arbitrage du demandeur)
scripts/pm-task-think.py <id> --question "…" --bloque L1 --urgence haute
scripts/pm-task-think.py <id> --feature "…" --domaine consignation --version V1 --lot L1
scripts/pm-task-think.py <id> --note "verbatim" --by M          # rarement à la main (le hook le fait)
scripts/pm-task-think.py <id> --set Q003 --state valide --dest D004   # trancher / trier
scripts/pm-task-think.py <id> --show                            # Q ouvertes, D récentes, compteurs
scripts/pm-think-merge.py [--project <client>/<projet>] [--check]   # fusion vers docs/cdc-*.md
scripts/pm-think-classify.py --session <sid>            # RM3067 : le tri par un modèle léger (rapport)
scripts/pm-think-classify.py --session <sid> --apply    # … et on consigne ce qu'il retient
scripts/pm-think-classify.py --all --since 2026-09-01   # reprise (LLM_BASE_URL → local ; sinon OLLAMA_HOST ; sinon API ; sinon claude -p)
scripts/pm-think-merge.py --rename-legacy                       # anciens cdc-<prefix>-NN-*.md → noms génériques
```

`--state` : `valide` ✅ · `invalide` ❌ · `propose` 🟡 · `attente` 🕐 · `reserve` ⏸.
Chaque ligne porte date, auteur (M = Mathieu / demandeur, A = agent) et session ; les ids sont
locaux au ticket (D001…) et préfixés `RM<id>-` à la fusion. Un texte contenant `|` est neutralisé.

## Gardes

- **Jamais de réflexion dans le `.log.md`** (événements) ni de prose dans le frontmatter (compteurs seuls).
- Une décision qui engage d'autres tickets est **fusionnée** vers le projet par le script, jamais recopiée à la main.
- `pm-task-status-update <id> ferme` refuse s'il reste une Q ouverte ou une N à trier (`--ignore-think` pour passer outre, consciemment).
