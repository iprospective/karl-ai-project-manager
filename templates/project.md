---
schema_version: "1.3.0"
slug: ""                       # identifiant kebab-case
name: ""
client: ""                     # slug du client parent
status: active                 # active | paused | archived
created: 2026-04-27

# Override possibles des valeurs héritées du client
defaults:
  priority: normal             # null → hérite du client
  team: []                     # vide → hérite du client, sinon merge ou override

# Intégrations
redmine:
  instance:                    # null → hérite du client
  project_id:
gitlab:
  repo: ""                     # repo de code (différent du repo PM)
  group:                       # null → hérite du client
  default_branch: main

# Stack technique
stack:
  language: ""                 # ex: python, php, javascript
  framework: ""                # ex: django, symfony, react
  database: ""                 # ex: postgresql, mysql
  tests:
    framework: ""              # ex: pytest, phpunit, jest
    command: ""                # ex: pytest -v, npm test
    coverage_min: 0            # seuil minimum de couverture (%)
---

## Description
<!-- Ce que fait ce projet, son périmètre, ses utilisateurs -->

## Objectifs
<!-- Ce qu'on cherche à accomplir, KPIs si applicable -->

## Structure / Fonctionnement
<!-- Architecture, conventions, patterns utilisés
     RÉDIGÉ ET ENRICHI AUTOMATIQUEMENT PAR L'AGENT summarizer -->

## Équipe
<!-- Surchargée ou ajoutée à l'équipe héritée du client -->
| Username | Email | Rôle |
|---|---|---|

## Ressources
<!-- Liens vers staging, prod, monitoring, doc, accès -->

## Notes
<!-- Décisions d'architecture, contexte important, contraintes -->
