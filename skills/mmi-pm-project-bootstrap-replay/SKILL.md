---
name: mmi-pm-project-bootstrap-replay
description: Relance le bootstrap d'un projet PM existant : re-propose les templates `bootstrap-tasks/` non encore appliqués (déjà filtré sur `bootstrap.done[]`). Utile pour ajouter plus tard les templates non-default (stack, deployment, testing, monitoring) quand le projet a vécu un peu. Usage : "/mmi-pm-project-bootstrap-replay" depuis un workspace, ou avec le path.
allowed-tools: Bash, Read, AskUserQuestion
---

# Skill : mmi-pm-project-bootstrap-replay

Wrapper contextuel autour de `scripts/pm-project-bootstrap.py`. Suit la convention `mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

## Quand déclencher

- "relance le bootstrap du projet"
- "propose-moi les bootstrap-tasks non faites"
- `/mmi-pm-project-bootstrap-replay`

## Détection contexte

Détection du projet courant via `cwd` (symlink `mmi-pm` ou `.mmi-pm` ou position dans `<projects_root>/clients/<E>/projects/<P>/`). Pas besoin de demander à l'utilisateur si le contexte est résolvable.

## Invocation

```bash
scripts/pm-project-bootstrap.py <project-pm-dir> [--yes] [--include ID] [--exclude ID]
```

## Exemples

```bash
# Auto-détecte le projet depuis cwd
# (résoudre le project_pm_dir via symlink mmi-pm/.mmi-pm)
./pm-project-bootstrap.py $(readlink -f .mmi-pm 2>/dev/null || readlink -f mmi-pm)

# Avec path explicite
./pm-project-bootstrap.py projects/clients/X/projects/Y/

# Forcer inclusion d'un template
./pm-project-bootstrap.py PATH --include 004-stack --include 005-deployment

# Mode --yes (prend tous les applicables par défaut)
./pm-project-bootstrap.py PATH --yes
```

## Notes

Le script `pm-project-bootstrap.py` filtre déjà les templates dans `bootstrap.done[]` et `bootstrap.skip[]`. Pour l'auto-detection : depuis un workspace, suivre `.mmi-pm`/`mmi-pm` symlink puis passer le chemin résolu.
