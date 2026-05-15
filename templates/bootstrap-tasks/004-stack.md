---
bootstrap_template: "004-stack"
default_checked: false
title: "Setup : documenter la stack technique"
type: documentation
priority: normal
tags: [bootstrap, stack, documentation]
roi:
  immediate_benefit: 2
  monthly_benefit: 3
estimate:
  difficulty: low
  time_minutes: 45
applicable_when: |
  `project/stack.md` n'existe pas. Particulièrement utile pour les projets non triviaux
  (plusieurs langages, framework, dépendances spécifiques).
---

## Contexte

Documenter la stack permet à un nouvel agent (ou humain) de comprendre rapidement les
choix techniques, contraintes de version, et conventions à respecter. Évite que chaque
nouvel intervenant doive grep / re-deviner.

## Critères d'acceptation

- [ ] `project/stack.md` existe (depuis `templates/aspects/common/stack.md`)
- [ ] Langages et runtimes (versions précises) documentés : ex: PHP 7.4, Ruby 3.3.7,
      Node 20, Python 3.11
- [ ] Framework principal et version : ex: Rails 8.1, Symfony 6.4, Django 5
- [ ] BDD (type, version, ORM utilisé)
- [ ] Dépendances notables (packages versions critiques, packages non standards)
- [ ] Outils de build/dev (bundler, composer, npm/yarn/pnpm, asset pipeline)
- [ ] Conventions de code (PSR-12, PEP-8, ESLint config, prettier, etc.)
- [ ] Particularités locales (forks, monkey patches, plugins critiques)

## Instructions

1. Copier `templates/aspects/common/stack.md` vers `project/stack.md`
2. Renseigner les sections
3. Inclure les versions exactes des composants critiques (Gemfile.lock, package-lock,
   composer.lock, requirements.txt extraits)

## Références

- `templates/aspects/common/stack.md`
- Les fichiers de lock du projet (Gemfile.lock, composer.lock, etc.)
