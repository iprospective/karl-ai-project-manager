---
bootstrap_template: "006-testing"
default_checked: false
title: "Setup : documenter la stratégie de tests"
type: documentation
priority: normal
tags: [bootstrap, testing, quality]
roi:
  immediate_benefit: 2
  monthly_benefit: 3
estimate:
  difficulty: low
  time_minutes: 30
applicable_when: |
  Le projet a (ou devrait avoir) une suite de tests automatisés non documentée.
---

## Contexte

NORMS exige des tests pour `feature`/`bugfix` (test-first, exécution par le reviewer
avant validation). Documenter la stratégie permet aux workers et reviewer de savoir
exactement quoi exécuter et avec quels outils.

## Critères d'acceptation

- [ ] `project/testing.md` existe (depuis `templates/aspects/common/testing.md`)
- [ ] Frameworks de test utilisés (RSpec, PHPUnit, pytest, Jest, Cypress, etc.)
- [ ] Commande exacte pour lancer la suite complète
- [ ] Commande pour lancer un test ciblé
- [ ] Conventions de nommage et de localisation des tests (`spec/`, `tests/`, etc.)
- [ ] Coverage cible si applicable (et comment la mesurer)
- [ ] Fixtures, factories, seeds : où, comment, conventions
- [ ] Tests E2E / intégration : outil, commande, prérequis (BDD test, browser, etc.)
- [ ] Note sur les tests "expensifs" (slow, requiring net, requiring infrastructure)

## Instructions

1. Copier `templates/aspects/common/testing.md` vers `project/testing.md`
2. Documenter chaque niveau de tests (unit, integration, e2e) du projet
3. Lister les commandes exactes (pas de pseudo-code)

## Références

- `templates/aspects/common/testing.md`
- `norms/NORMS.md` § "Reviewer doit exécuter les tests"
- `agents/worker-dev.md` (règles test-first)
