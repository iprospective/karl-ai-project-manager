---
schema_version: "1.6.0"
slug: ""                       # identifiant kebab-case (= nom du dossier)
name: ""
type: client                   # client (tiers commercial) | product (écosystème) | self (interne / perso)
status: active                 # active | paused | archived
created: 2026-04-27

# Contacts du client (RM2702) — outil : `pm-client-contact.py add|list|set|remove`
# Champs : last_name (NOM), first_name (prénom), email, phone (chaîne : le « + » et
# les zéros de tête comptent), role (owner|decideur|technique|facturation|autre).
# `internal: true` marque NOS adresses : posé automatiquement, elles n'identifient
# aucun client et ne servent jamais à router un email entrant (RM2669).
contacts:
  - last_name: ""
    first_name: ""
    email: ""
    phone: ""
    role: owner

# Cascade — valeurs héritées par tous les projets du client
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

# Aspects activés (informatif — la présence du fichier suffit)
aspects:
  - overview
  # - hosting
  # - contracts
  # - sla
---

## Description
<!-- Activité du client, contexte global, secteur, taille -->

## Aspects documentés
<!-- Sommaire des fichiers présents dans ce dossier client/
     Mis à jour automatiquement par l'agent summarizer.
     Exemple :
     - [hosting.md](hosting.md) — infra par défaut
     - [contracts.md](contracts.md) — références contractuelles -->

## Notes
<!-- Mémo libre — décisions importantes, contexte historique -->
