# runtime·schema — cascade, nommage, frontmatter, énumérations
Ouvrir quand : je crée/édite une fiche, je remplis un frontmatter, je cherche une valeur permise. Source : `norms/src/NORMS-KERNEL.md` (fin).

## Cascade client → projet → tâche
Valeurs héritées par défaut ; un enfant surcharge en redéfinissant ; sections texte (Description, Structure…) s'additionnent. Héritables : `team`, `defaults.priority`, `gitlab.group`, `gitlab.default_branch`, `redmine.instance`, contraintes globales.
Lecture du contexte (worker, summarizer, reviewer) : 1 système `NORMS.md` + `agents/worker-common.md` + `agents/worker-{role}.md` · 2 client `{entity_client_dir}/*.md` + `{entity_memory_dir}/*.md` · 3 projet `{project_dir}/*.md` + `{docs_dir}/*.md` + `{project_memory_dir}/*.md` · 4 tâche `paths.task_file` + `paths.task_log_file`. Chemins via `pm.config.yml` (défaut `{projects_root}/clients/{C}/...`).

## Nommage
Tâche `RM{id}_{titre-kebab}.md` · journal `RM{id}_{titre-kebab}.log.md` · overview projet `project/overview.md` · overview client `client/overview.md`.

## Frontmatter tâche (template `templates/task.md`)
Obligatoires : `schema_version`, `redmine_id`, `title`, `type`, `creator`, `status`, `priority`, `created`.
Conditionnels : `bug.*` si `type: bugfix` · `git.*` si dev · `test_url` si env de test · `deploy_actions` si déploiement · `close_reason` obligatoire si `status: ferme` · `requires_agent_test` = `default`(défaut)|`oui`|`non`|`demander` : conditionne la passe agent-testeur en fin de dev (CF Redmine 27 ; absent ⇔ `default`).

## Énumérations
- type : `audit` `feature` `bugfix` `refactoring` `documentation` `security` `performance` `infrastructure` `configuration` `database` `design` `research` `maintenance` `assistance`
- status : `a_etudier_chiffrer` `etude_chiffrage_en_cours` `etude_chiffrage_a_valider` `a_faire` `en_cours` `a_tester_dev` `a_tester_demandeur` `a_mep` `en_mep` `en_pause` `a_corriger` `ferme` ; `a_tester_verifier` déprécié = alias lecture de `a_tester_demandeur`
- priority : `low` `normal` `high` `urgent`
- close_reason : `resolu` `abandonne` `doublon` `wont_fix` `invalide` `hors_perimetre`
- bug.reproducibility : `always` `often` `sometimes` `rarely` `never`
- estimate.difficulty : `low` `medium` `high` `critical`
- pistes.type : `automation` `amélioration` `sécurité` `performance` `intégration` `documentation` · pistes.effort : `low` `medium` `high`
- roi.immediate_benefit / roi.monthly_benefit : 1 (négligeable) → 5 (critique)
- target_env : `null` `local` `dev` `test` `staging` `prod` `demo` `qa` `sandbox` `<custom-kebab-case>` ; doit correspondre à un `environments[].name` de `project/environments.md` (ou `client/environments.md` en cascade) ; custom si env spécifique (`staging-eu`, `prod-canary`) ; `preprod` = alias accepté de `staging` (canonique `staging`).
