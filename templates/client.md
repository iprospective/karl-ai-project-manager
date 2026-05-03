---
schema_version: "1.3.0"
slug: ""                       # identifiant kebab-case
name: ""                       # nom affichable
status: active                 # active | paused | archived
created: 2026-04-27

# Contacts
contacts:
  - name: ""
    email: ""
    role: owner

# Cascade — valeurs héritées par tous les projets du client (override possible)
defaults:
  priority: normal
  team:
    - username: iprospective
      email: mathieu@iprospective.fr
      role: owner

# Intégrations héritées
gitlab:
  group: ""
  default_branch: main
redmine:
  instance:                    # null → hérite de ${REDMINE_URL}
  default_project_id:
---

## Description
<!-- Activité du client, contexte global, secteur, taille -->

## Structure / Fonctionnement
<!-- Comment ce client opère : processus, points de contact, contraintes structurelles
     RÉDIGÉ ET ENRICHI AUTOMATIQUEMENT PAR L'AGENT summarizer -->

## Contraintes
<!-- Légales, techniques, contractuelles, SLA -->

## Notes
<!-- Mémo libre — décisions importantes, contexte historique -->
