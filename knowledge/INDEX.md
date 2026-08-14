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
- [zabbix](./zabbix/) — API JSON-RPC (search=faux négatifs, FQDN), triggers figés/nodata,
  manual_close, items dépendants
- [gitlab](./gitlab/) — API : gotcha `%2F` (Apache), résolution de projet (search non
  fiable, matcher le path complet — cf. RM2219), MR ; dépôts & groupes : les modules
  PrestaShop mutualisés sont sous `prestashop/` (groupe 109), et l'ancien chemin
  `iprospective/prestashop/…` **redirige** — un dépôt récent y semble donc « inexistant »
- [gnupg](./gnupg/) — gpg-agent en émulation ssh-agent : pièges headless/LXC
  (`agent refused operation`), bascule vers un vrai ssh-agent
- [karl-agent](./karl-agent/) — sessions Claude Code du cockpit : stockage
  (transcript partagé hôte↔conteneur, store per-session NON partagé), les 3 ancrages
  d'une session à un projet, déplacer une session (`/move-session`, `karl-move-session`)

## Règles transverses

- **Les endpoints `search` des API ne sont PAS fiables pour l'inventaire** : ils peuvent
  renvoyer des faux négatifs **silencieux** (0 résultat alors que l'objet existe — vécu
  sur GitLab `/projects?search=` ET Zabbix `trigger.get`/`item.get search`). Pour toute
  résolution/inventaire dont dépend une décision : **énumérer large** (pagination,
  scope membership/hostids) **et filtrer côté client** sur l'identifiant COMPLET
  (path_with_namespace, FQDN…), jamais sur un basename. 0 ou >1 match exact = erreur
  explicite, pas de fallback silencieux. Détails : [gitlab/api.md](./gitlab/api.md),
  [zabbix/api.md](./zabbix/api.md).
- **« Introuvable » ne prouve pas « inexistant »** : sur un chemin obsolète mais
  **redirigé**, un objet ancien répond et un objet récent renvoie la **même erreur**
  qu'un objet qui n'existe pas — et un test-témoin ancien *valide* le mauvais chemin.
  Avant de conclure à l'absence et de (re)créer : chercher au chemin **canonique** et
  **énumérer** le conteneur. Détails :
  [gitlab/depots-et-groupes.md](./gitlab/depots-et-groupes.md).

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
