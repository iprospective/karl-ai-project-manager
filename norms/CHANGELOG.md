# Changelog des normes

Toutes les évolutions notables sont documentées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/)

---

## [1.1.1] - 2026-04-27

### Modifié
- Règle de versionning : les versions **mineures** sont désormais archivées dans `archive/` (comme les majeures). Seuls les patches restent sans archive.
- Description du dossier `archive/` mise à jour en conséquence

### Ajouté
- `archive/NORMS_v1.0.md` — snapshot de la version initiale
- `archive/NORMS_v1.1.md` — snapshot de la v1.1

---

## [1.1.0] - 2026-04-27

### Ajouté
- Section **Collaboration multi-agents** complète :
  - Principe fondamental : Redmine comme mutex, MD comme contexte de travail
  - Définition des rôles : orchestrateur, workers spécialisés, reviewer
  - Table des règles d'écriture par rôle et type de fichier
  - Protocole de prise en charge d'une tâche (10 étapes)
  - Gestion des sous-tâches multi-niveaux avec propagation bottom-up du `completion_pct`
  - Protocole optimistic locking sur le champ `updated`
  - Règles append-only pour les `.log.md`
- Section **Architecture de déploiement** complète :
  - V1 : machine unique (actuelle)
  - V1.5 : NFS sur ZFS pour ajout de serveurs sans refonte
  - V2 : Git/branches GitLab pour distribution robuste
  - Tableau de sélection selon contexte

---

## [1.0.0] - 2026-04-26

### Initial
- Structure de dossiers et conventions de nommage
- Schéma frontmatter complet pour les tâches
- Machine d'états avec 7 statuts et transitions validées
- Séparation tâche (stable) / journal append-only (.log.md)
- Champs ROI : `immediate_benefit` + `monthly_benefit` (/5)
- Estimation IA : `difficulty`, `time_minutes`, `tokens`, `confidence`
- Suivi tokens et temps cumulés (`tokens_total`, `time_total_minutes`)
- `status_history` avec modèle IA, tokens et durée par étape
- Support sous-tâches : `parent_task` + `sub_tasks[]`
- Champ `pistes[]` structuré pour idées futures (label, type, effort)
- Références externes `refs[]` (Redmine partenaire, docs, URLs)
- Intégration GitLab : `git.repo`, `git.branch`, `git.mr_url`
- Environnement de test : `test_url`
- Actions de déploiement : `deploy_actions[]`
- Champs bug : `reproducibility` + `reproduce_steps` + `conditions`
- Templates task.md et project.md
- Configuration globale GitLab dans NORMS.md
