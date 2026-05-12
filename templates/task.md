---
schema_version: "1.5.2"

# Identification
redmine_id:                   # OBLIGATOIRE — entier, doit correspondre au RM{id} du nom de fichier
redmine_last_journal_id: null # int — id du dernier journal Redmine consulté (rempli par redmine-fetch-task / fetch-updates)
redmine_last_checked_at: null # str ISO — timestamp du dernier check Redmine
title: ""
type: feature
# audit | feature | bugfix | refactoring | documentation | security
# performance | infrastructure | database | design | research | maintenance | assistance
parent_task: null
sub_tasks: []

# Personnes
creator: iprospective
team:
  - username: iprospective
    email: mathieu@iprospective.fr
    role: owner

# Statut
status: a_etudier_chiffrer
# a_etudier_chiffrer | etude_chiffrage_en_cours | a_faire | en_cours
# a_tester_verifier | a_corriger | ferme
close_reason: null
# resolu | abandonne | doublon | wont_fix | invalide | hors_perimetre
completion_pct: 0

# Priorité & ROI
priority: normal
# low | normal | high | urgent
roi:
  immediate_benefit: 3    # /5 — valeur produite immédiatement
  monthly_benefit: 2      # /5 — valeur récurrente mensuelle

# Estimation (calculée par IA lors du chiffrage)
estimate:
  difficulty: null        # low | medium | high | critical
  time_minutes: null
  tokens: null
  confidence: null        # 0.0 → 1.0
  estimated_by: null
  estimated_at: null

# Bug uniquement (si type: bugfix)
bug:
  reproducibility: always # always | often | sometimes | rarely | never
  reproduce_steps: |
    1.
    2.
  conditions: ""

# Dépendances
depends_on: []
blocks: []

# Références externes
refs: []
# - type: redmine_partner | redmine | doc | url | gitlab | jira | autre
#   url:
#   label: ""

# Environnement & déploiement
test_url: null
git:
  repo: null              # ex: git@gitlab.iprospective.fr:org/repo.git
  branch: null            # ex: feature/RM1234-titre
  mr_url: null            # ex: https://gitlab.iprospective.fr/org/repo/-/merge_requests/42
deploy_actions: []
# - "Description de l'action à effectuer au déploiement"

# Métriques cumulées (agrégées depuis status_history)
tokens_total: 0
time_total_minutes: 0

# Dates
created: 2026-04-26
due: null
updated: 2026-04-26

# Historique des statuts
status_history:
  - status: a_etudier_chiffrer
    at: 2026-04-26T09:00
    by: iprospective
    model: null
    tokens: null
    duration_minutes: null

# Pistes futures
pistes: []
# - label: ""
#   type: automation | amélioration | sécurité | performance | intégration | documentation
#   effort: low | medium | high

tags: []
---

## Contexte
<!-- Pourquoi cette tâche existe, quel problème elle résout -->

## Critères d'acceptation
- [ ]
- [ ]

## Instructions
<!-- Étapes, contraintes, ressources, accès nécessaires -->

## Références
<!-- Liens utiles, documentation, maquettes, specs -->
