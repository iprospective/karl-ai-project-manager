---
bootstrap_template: "003-environnements"
default_checked: true
title: "Setup : documenter les environnements (dev/test/staging/prod)"
type: infrastructure
priority: high
tags: [bootstrap, environments, infrastructure]
roi:
  immediate_benefit: 4
  monthly_benefit: 4
estimate:
  difficulty: medium
  time_minutes: 60
applicable_when: |
  `project/environments.md` n'existe pas, OU `environments[]` est vide, OU au moins
  un environnement a des champs critiques manquants (url, host, app_path, branch).
---

## Contexte

Tout projet a au moins un environnement (prod), souvent plusieurs (dev, test, staging,
prod). Ces environnements doivent être documentés dans `project/environments.md`
pour que les agents et humains puissent :

- Naviguer entre les envs sans se tromper
- Connaître les URLs, hosts, branches, logs associés
- Résoudre les secrets via `secrets_source`

Référence : `norms/NORMS.md` § "Environnements (aspect `environments.md`)".

## Critères d'acceptation

- [ ] `project/environments.md` existe (depuis `templates/aspects/common/environments.md`)
- [ ] Au minimum un environnement `prod` est déclaré
- [ ] Les environnements applicables (dev, test, staging, demo, qa, sandbox)
      sont déclarés avec leurs champs renseignés :
  - `name`, `status`, `url`, `host`, `user`, `app_path`, `branch`
  - `logs.app` et `logs.fpm` si applicable
  - `secrets_source` (renvoie vers Vaultwarden, ou null si setup secrets pas encore fait)
- [ ] Le tableau `env_vars[]` liste les variables d'environnement attendues (sans
      valeurs) avec description + envs où elles existent
- [ ] La section "Procédure de déploiement par env" décrit comment déployer/restart
      pour chaque env
- [ ] La section "Accès et credentials" pointe vers Vaultwarden ou explique où trouver

## Instructions

1. Copier `templates/aspects/common/environments.md` vers `project/environments.md`
2. Pour chaque environnement existant, renseigner les champs du frontmatter
3. Lister les variables d'environnement (sans valeurs) dans `env_vars[]`
4. Rédiger les procédures de déploiement par env
5. Si la tâche `001-secrets-vaultwarden` est aussi à faire, coordonner pour que
   `secrets_source` soit renseigné en cohérence

## Références

- `templates/aspects/common/environments.md`
- `norms/NORMS.md` § "Environnements (aspect `environments.md`)" + § "target_env"
- `templates/aspects/common/hosting.md` (provider/coûts/DNS, complémentaire)
