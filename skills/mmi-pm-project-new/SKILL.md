---
name: mmi-pm-project-new
description: Pipeline complet de création de projet PM : crée projet Redmine sous parent, ajoute 2 memberships par défaut (Admin/Manager, iProspective/Intervenant), crée struct PM, écrit overview.md (+ environments.md si --with-environments), crée symlinks bidirectionnels workspace ↔ PM, lance bootstrap. C'est l'automatisation du flow manuel utilisé pour nc-clients. Usage : "/mmi-pm-project-new --client X --slug Y ...".
allowed-tools: Bash, Read, AskUserQuestion
---

# Skill : mmi-pm-project-new

Wrapper contextuel autour de `scripts/pm-project-new.py`. Suit la convention `mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

## Quand déclencher

- "crée le projet X pour le client Y"
- "nouveau projet PM"
- `/mmi-pm-project-new --client ... --slug ... --workspace ...`

## Détection contexte

Détection du projet courant via `cwd` (symlink `mmi-pm` ou `.mmi-pm` ou position dans `<projects_root>/clients/<E>/projects/<P>/`). Pas besoin de demander à l'utilisateur si le contexte est résolvable.

## Invocation

```bash
scripts/pm-project-new.py --client X --slug Y --name "..." --workspace /path --redmine-parent Z
```

## Exemples

```bash
# Projet sous client product (parent Redmine = outils)
./pm-project-new.py --client nextcloud --slug nc-mmi --name "Nextcloud — interne" \
  --workspace /zfs/workspaces/nextcloud/nc-mmi --redmine-parent outils \
  --with-environments

# Projet bootstrap minimal (sans environments, bootstrap interactif)
./pm-project-new.py --client iprospective --slug pm-validator --name "PM Validator" \
  --workspace /zfs/workspaces/ai/foo --redmine-parent pm-ai-agents --interactive-bootstrap

# Sans bootstrap
./pm-project-new.py --client X --slug Y --name "..." --workspace /path \
  --redmine-parent Z --no-bootstrap
```

## Notes

**Branches protégées (RM2057)** : une fois le dépôt `-core` publié, le script applique `pm-protect` au dépôt créé et aux dépôts de code du workspace (`repos/*.git`) qui ont déjà un remote de forge. Étape non bloquante — si elle échoue (droits *manager* manquants, forge tierce), le projet est créé quand même et la commande de rattrapage est affichée : `pm-protect.py --repo <dépôt>`.

Utilise `REDMINE_USER_MAIN_API_KEY` (Karl) pour les ops Redmine de meta (création projet, memberships). Le `--redmine-parent` peut être un id numérique ou un identifier (ex `outils`). Le bootstrap est `--yes` par défaut (tâches default_checked applicables uniquement), `--interactive-bootstrap` pour choisir.
