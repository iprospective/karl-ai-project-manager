---
schema_version: "1.5.2"

# Identification
redmine_id: 9999
redmine_last_journal_id: 12345
redmine_last_checked_at: 2026-04-27T10:00
title: "Exemple de tâche complète et conforme au schéma"
type: feature
parent_task: null
sub_tasks: []

# Personnes
creator: iprospective
team:
  - username: iprospective
    email: mathieu@iprospective.fr
    role: owner
  - username: agent-dev
    role: executor

# Statut
status: en_cours
close_reason: null
completion_pct: 40

# Priorité & ROI
priority: high
roi:
  immediate_benefit: 4
  monthly_benefit: 3

# Estimation
estimate:
  difficulty: medium
  time_minutes: 60
  tokens: 8000
  confidence: 0.7
  estimated_by: claude-sonnet-4-6
  estimated_at: 2026-04-27T10:00

# Dépendances
depends_on: []
blocks: []

# Références externes
refs:
  - type: doc
    url: https://example.com/spec
    label: "Spec fonctionnelle"

# Environnement & déploiement
test_url: null
git:
  repo: git@gitlab.iprospective.fr:iprospective/exemple.git
  branch: feature/RM9999-exemple
  mr_url: null
deploy_actions:
  # Procédure de MEP du ticket : l'ordre de la liste EST l'ordre d'exécution.
  - "Snapshot ZFS du conteneur depuis l'hôte (point de restauration préalable)"
  - "Jouer la migration 2026-08-25-demo-flag.sql — AVANT tout déploiement de code, sinon l'UPDATE échoue en silence"
  - "Déployer le code (MR mergée dans la branche de prod), puis recharger PHP-FPM"
  - "Lancer scripts/backfill-demo.php --go une fois — POINT DE NON-RETOUR : le flag est recalculé pour toutes les fiches"
  - "Contrôle : la colonne « Demo » apparaît dans la liste et le filtre booléen répond"
  - "Rollback : revenir au commit précédent + DROP de la colonne (aucune autre donnée touchée)"
implementation: |
  Exemple de la maille attendue : concret, court, orienté « où ça se greffe ».
  Obligatoire dès que l'étude débouche sur du code, même pour un petit dev.

  **Modèle de données** — `llx_exemple_extrafields.demo_flag` (`TINYINT(1)`) : marque
  les fiches traitées ; déclaré dans `llx_extrafields` avec `list=1` (visible et
  filtrable en liste). Aucune table nouvelle.

  **Composants**
  | Fichier : point d'insertion | Modification |
  |---|---|
  | `src/demo/collect.inc.php::collect_data()` | ajouter la clé `demo_flag` au tableau retourné |
  | `src/demo/map.inc.php::map_update()` | mapper `demo_flag` vers l'extrafield cible |
  | `scripts/backfill-demo.php` | **à créer** — initialisation rejouable, `--dry-run` par défaut |

  **Vues** — liste des fiches (`tpl/liste.tpl.php`) : une colonne + un filtre booléen,
  sur le modèle exact de la colonne `code_client` existante (4 retouches localisées :
  `$filter_list`, `$cols_list`, le `SELECT`, l'en-tête + la cellule).

  **Flux & déclencheurs** — la modification d'une fiche déclenche déjà `collect_data()` ;
  rien à ajouter. Le backfill se lance à la main, une fois, après création de la colonne.

  **Migration** — colonne créée **avant** la première synchro, sinon l'`UPDATE` échoue
  en silence. Script d'installation rejouable (`ADD COLUMN` + `INSERT ... WHERE NOT EXISTS`).

  **Pièges** — le retrait d'un marquage doit **remettre le flag à 0** : recalculer
  systématiquement à chaque passage, jamais de mise à jour conditionnelle « si non vide ».

# Métriques cumulées
tokens_total: 3200
time_total_minutes: 15

# Dates
created: 2026-04-27
due: 2026-05-04
updated: 2026-04-27T14:00

# Historique
status_history:
  - status: a_etudier_chiffrer
    at: 2026-04-27T09:00
    by: iprospective
  - status: etude_chiffrage_en_cours
    at: 2026-04-27T09:30
    by: agent-dev
    model: claude-sonnet-4-6
    tokens: 1200
    duration_minutes: 5
  - status: a_faire
    at: 2026-04-27T10:00
    by: iprospective
  - status: en_cours
    at: 2026-04-27T14:00
    by: agent-dev
    model: claude-sonnet-4-6
    tokens: 2000
    duration_minutes: 10

# Pistes futures
pistes:
  - label: "Auto-création de la branche GitLab au passage en_cours"
    type: automation
    effort: low

tags: [exemple, demo]
---

## Contexte
Ce fichier est un exemple complet et valide de tâche, utilisé par la CI
pour vérifier que le validateur fonctionne correctement.

## Critères d'acceptation
- [x] Le fichier passe la validation `scripts/validate-task.py`
- [ ] Le fichier illustre tous les champs courants

## Instructions
Aucune action requise — fichier de démonstration uniquement.

## Références
- [norms/NORMS.md](../norms/NORMS.md)
