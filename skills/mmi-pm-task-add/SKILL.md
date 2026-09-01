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
./pm-task-add.py --title "Ajouter le filtre X" --type feature --priority high \
  --description "Détails..." --tags "cockpit"

# BUGFIX : les étapes de reproduction sont OBLIGATOIRES (RM2752). `validate-task`
# les impose (`bug.reproduce_steps`) — sans elles le ticket naîtrait invalide, et
# un bug sans repro se rouvre trois fois. `--bug-reproducibility` vaut `always`
# par défaut (always|often|sometimes|rarely|never).
./pm-task-add.py --title "Corriger bug X" --type bugfix --priority high \
  --description "Ce qu'on observe, et ce qu'on attendait" \
  --bug-steps "1. lancer la commande
2. observer l'erreur" \
  --bug-reproducibility always

# Étapes longues : les lire depuis un fichier plutôt que de les tasser en argv.
# Un seul flux stdin : si `--description -` le consomme, passer les étapes par
# fichier ou en argument (le script le dit plutôt que de poser des étapes vides).
./pm-task-add.py --title "…" --type bugfix --bug-steps-file repro.md

# Override projet
./pm-task-add.py --project iprospective/pm-ai-agents --title "..." --type feature

# Capture fiable de l'id créé pour enchaîner (--porcelain : id nu sur stdout,
# logs sur stderr) — JAMAIS prédire un RM-id de mémoire (tripwire #13).
ID=$(./pm-task-add.py --title "Nouvelle tâche" --type feature --porcelain)
./pm-task-status-update.py "$ID" en_cours
./pm-branch-start.py "$ID" --take
```

## Notes

Types : liste canonique via `pm-task-add.py --list-types` (bugfix, feature, configuration, infrastructure, maintenance, …). Priorities : low, normal, high, urgent. Mapping vers Redmine tracker/priority géré automatiquement.

`--type bugfix` **refuse** de créer sans `--bug-steps` / `--bug-steps-file` : c'est
volontaire. Le ticket sortait sinon invalide au regard de `validate-task`, avec un
warning à la création et un remède qui ne menait nulle part. Les `--bug-*` sur un
autre type sont refusés aussi — une faute de frappe vaut mieux dite que silencieuse.

Si un warning `validate` apparaît malgré tout, le remède affiché est
`scripts/validate-task.py <chemin du MD>` : il donne le détail, champ par champ.

**`--start-branch [--branch-repo PATH]`** : verbe atomique (RM2224) — crée le ticket PUIS enchaîne `pm-branch-start --take` (branche + prise en_cours) avec l'id capturé en interne : zéro manipulation d'id par l'agent. À préférer dès qu'on va coder le ticket. Incompatible avec `--retro`/`--status`.

**`--porcelain` (alias `--id-only`)** : n'imprime que l'**id nu** du ticket créé sur stdout (tous les logs vont sur stderr). À utiliser dès qu'on **enchaîne** sur le ticket (status-update, branch-start, task-link) : capturer `ID=$(pm-task-add … --porcelain)` puis consommer `$ID`. Ne jamais saisir un RM-id de mémoire — la séquence Redmine est globale à l'instance, le prochain id n'est pas prévisible (NORMS tripwire #13).
