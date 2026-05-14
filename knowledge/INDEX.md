---
type: index
created: 2026-05-14
---

# Knowledge base — iprospective

Capitalisation transverse des connaissances techniques et opérationnelles, réutilisables
sur l'ensemble des clients et projets.

Cette knowledge se distingue de :
- `/zfs/workspaces/security/knowledge/` — capitalisation **sécurité** par produit (audits)
- `norms/` (de ce repo) — règles de fonctionnement du système de gestion de projets

Le contenu d'ici est **opérationnel/technique général** : comment marche un produit,
ses pièges, des procédures réutilisables (migration, déploiement, dépannage), etc.

## Index par produit / techno

- [redmine](./redmine/) — projet/issue tracking, wiki, API, migration Textile → Markdown

## Conventions

- Un dossier par produit (`redmine/`, `dolibarr/`, `prestashop/`…)
- À l'intérieur : `overview.md`, `api.md`, `gotchas.md`, et des fichiers thématiques pour
  procédures complexes (ex: `redmine/textile-to-markdown-migration.md`)
- Pas de duplication avec `security/knowledge/` — si un finding sécurité est lié à un
  comportement produit, mettre le finding côté sécurité et linker vers ici
- Lier entre fichiers via chemins relatifs

## Comment alimenter

Quand on apprend quelque chose de **non-trivial** sur un produit (un comportement
surprenant, une commande non documentée, un workaround), capitaliser ici plutôt que de
le re-découvrir à la prochaine occurrence. Garder les fichiers actionnables (pas de
blabla).
