---
bootstrap_template: "005-deployment"
default_checked: false
title: "Setup : documenter pipeline CI/CD et procédure de déploiement"
type: infrastructure
priority: normal
tags: [bootstrap, deployment, ci-cd]
roi:
  immediate_benefit: 2
  monthly_benefit: 4
estimate:
  difficulty: medium
  time_minutes: 60
applicable_when: |
  Le projet a au moins un déploiement à faire (staging/preprod/prod), et la procédure
  n'est pas documentée dans `project/deployment.md`.
---

## Contexte

Sans procédure documentée, chaque déploiement est un quasi-incident. Documenter le flow
exact (commandes, conditions, rollback) sécurise les déploiements et permet aux agents
de les exécuter de façon prévisible.

## Critères d'acceptation

- [ ] `project/deployment.md` existe (depuis `templates/aspects/common/deployment.md`)
- [ ] Pipeline CI/CD documenté (étapes : build, test, déploiement, vérifs post-deploy)
- [ ] Procédure de release : de la branche au prod (étapes, validations, fenêtres)
- [ ] Procédure de rollback : commandes exactes, RTO estimé
- [ ] Tableau des variables d'environnement (déjà couvert dans `environments.md`,
      réutiliser ou pointer)
- [ ] Migrations de schéma : comment elles sont jouées au déploiement (concurrence,
      idempotence)
- [ ] Feature flags : outil utilisé, conventions, lifecycle des flags

## Instructions

1. Copier `templates/aspects/common/deployment.md` vers `project/deployment.md`
2. Renseigner les sections en s'appuyant sur les scripts existants côté workspace
3. Si CI configurée (`.gitlab-ci.yml`, `.github/workflows/`), documenter les stages
4. Tester un rollback "à blanc" pour valider la procédure

## Références

- `templates/aspects/common/deployment.md`
- `project/environments.md` (envs cibles)
- `project/stack.md` (commandes du framework)
