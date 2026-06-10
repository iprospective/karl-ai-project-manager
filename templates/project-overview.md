---
schema_version: "1.7.1"
slug: ""                       # identifiant kebab-case (= nom du dossier)
name: ""
client: ""                     # OBLIGATOIRE — slug de l'entité parente (peut être type=client/product/self)
status: active                 # active | paused | archived
created: 2026-05-12

# Partage cross-client — source de vérité du frontmatter
used_by_clients: []            # entités qui consomment ce projet (typique pour les modules génériques)
provided_by: null              # pointeur vers le projet fournisseur, ex: "dolibarr/mmi-productcheck"

# Relation « implémentation » entre projets (many-to-many, listes)
implements: []                 # projets généraux que ce projet implémente, ex: ["iprospective/infrastructure"]
implemented_by: []             # projets qui implémentent celui-ci (côté projet général)

# Bootstrap — tracking des tâches d'initialisation projet
bootstrap:
  skip: []                     # IDs de templates jamais à proposer (ex: ["003-environnements"])
  done: []                     # IDs de templates déjà appliqués (rempli par pm-project-bootstrap.py)

# Override possibles des valeurs héritées du client
defaults:
  priority: normal             # null → hérite du client
  team: []                     # vide → hérite du client

# Intégrations Redmine (project_id obligatoire — lien dur MD ↔ Redmine)
redmine:
  instance:                    # null → hérite du client
  project_id:                  # OBLIGATOIRE — slug du projet Redmine
  subprojects: []              # optionnel — sous-projets Redmine rattachés
gitlab:
  repo: ""                     # repo de code (différent du repo PM)
  group:                       # null → hérite du client
  default_branch: main

# Aspects activés (informatif — la présence du fichier suffit)
aspects:
  - overview                   # ce fichier (toujours)
  # - stack
  # - hosting
  # - data-model
  # ...
---

## Description
<!-- Ce que fait ce projet, son périmètre, ses utilisateurs cibles -->

## Objectifs
<!-- Ce qu'on cherche à accomplir, KPIs si applicable -->

## Aspects documentés
<!-- Sommaire des fichiers présents dans ce dossier project/
     Mis à jour automatiquement par l'agent summarizer.
     Exemple :
     - [stack.md](stack.md) — langages, framework, dépendances
     - [hosting.md](hosting.md) — environnements, accès
     - [data-model.md](data-model.md) — schéma BDD -->

## Équipe
<!-- Surchargée ou ajoutée à l'équipe héritée du client -->
| Username | Email | Rôle |
|---|---|---|

## Notes
<!-- Décisions structurantes, contexte important, contraintes spécifiques -->
