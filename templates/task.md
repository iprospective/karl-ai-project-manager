---
schema_version: "1.12.0"

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
recurrence: null
# null | quotidienne | hebdomadaire | mensuelle | annuelle — ticket RÉCURRENT
# (vérification périodique rejouée : UN ticket rouvert à chaque passage, pas un
#  ticket par run). CF Redmine 7 « Recurrence » ; se pose via pm-task-recurrence.

# Priorité & ROI (cf. NORMS — section "ROI assisté par IA")
priority: normal
# low | normal | high | urgent
roi:
  immediate_benefit: 3      # /5 — qualitatif, valeur produite immédiatement
  monthly_benefit: 2        # /5 — qualitatif, valeur récurrente mensuelle
  immediate_gain_eur: null  # € — quantitatif (prime sur 1-5 si renseigné)
  monthly_gain_eur: null    # €/mois — quantitatif récurrent

# Estimation (calculée par IA lors du chiffrage)
estimate:
  difficulty: null            # low | medium | high | critical
  human_time_minutes: null    # temps humain prévu (revue, décisions, tests)
  ai_time_minutes: null       # temps wall-clock IA prévu
  time_minutes: null          # legacy, conservé pour compat
  tokens: null                # tokens prévus (total)
  cost_usd: null              # coût USD prévu (= tokens × prix modèle)
  estimated_model: null       # ex: claude-opus-4-7 (pour calcul cost prévu)
  confidence: null            # 0.0 → 1.0
  estimated_by: null
  estimated_at: null

# Bug uniquement (si type: bugfix)
bug:
  reproducibility: always # always | often | sometimes | rarely | never
  reproduce_steps: |
    1.
    2.
  conditions: ""

# Liens entre tâches (cf. NORMS — section "Liens entre tâches")
depends_on: []           # list[int] — RM-ids dont CETTE tâche dépend (B finit avant A)
blocks: []               # list[int] — RM-ids que CETTE tâche bloque (A finit avant B)
relates: []              # list[int] — RM-ids latéraux (même famille, non bloquant)

# Références externes (champ libre, pas de relation Redmine)
refs: []
# - type: redmine_partner | redmine | doc | url | gitlab | jira | autre
#   url:
#   label: ""

# Environnement & déploiement
target_env: null          # null | dev | test | staging | prod | demo | qa | sandbox  (preprod = alias staging)
                          # → précise l'env visé (déploiement, debug, ajustement spécifique)
                          # référence un `environments[].name` du project/environments.md
test_url: null            # URL où QA peut tester ; si null et target_env set,
                          # se déduit de environments.<target_env>.url
git:
  repo: null              # ex: git@gitlab.iprospective.fr:org/repo.git
  branch: null            # ex: feature/RM1234-titre
  mr_url: null            # ex: https://gitlab.iprospective.fr/org/repo/-/merge_requests/42
deploy_actions: []
# - "Description de l'action à effectuer au déploiement"

# Métriques cumulées effectives (auto-incrémentées par le hook pm-task-tick)
tokens_total: 0                # somme tous types
tokens_breakdown:              # détail par type pour audit
  input: 0
  output: 0
  cache_read: 0
  cache_creation: 0
cost_total_usd: 0.0            # cumulé USD (recalculé à chaque tick depuis pricing.yml)
human_time_total_minutes: 0    # temps humain effectif
ai_time_total_minutes: 0       # temps wall-clock IA effectif
time_total_minutes: 0          # legacy = human + ai (compat ascendante)

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
