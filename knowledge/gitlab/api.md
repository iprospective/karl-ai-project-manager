---
type: knowledge
product: gitlab
created: 2026-07-10
---

# GitLab (gitlab.iprospective.fr) — API : pièges de résolution de projet

Tokens : `.env` du repo PM (`GITLAB_MANAGER_TOKEN` = karl, repos PM/branches protégées ;
`GITLAB_WORKER_TOKEN` = karl-dev, repos de code).

## ⚠ Piège n°1 : `%2F` interdit (Apache)

L'instance est derrière Apache qui **rejette tout slash encodé** : une URL d'API contenant
`%2F` (`/projects/group%2Fname`) renvoie un **404 Apache (HTML)** avant même d'atteindre
GitLab — faux diagnostic « droits manquants » garanti. **Toujours résoudre l'ID numérique**
du projet et n'adresser que `/api/v4/projects/<id>/…`.

## ⚠ Piège n°2 : `?search=` = faux négatifs SILENCIEUX

`GET /projects?search=<nom>` peut **rater des projets existants** : vécu 2026-07-10,
`iprospective/infra-core` (id 134) absent de `search=infra-core` ET de `search=core`,
alors qu'il apparaît dans l'énumération paginée et que git y accède avec le même token.

**Règle : ne jamais résoudre un projet par `?search=` seul.** Énumérer paginé
(`GET /projects?membership=true&per_page=100&page=N`, suivre `X-Next-Page`) et matcher le
**`path_with_namespace` COMPLET** (déduit du remote git) — jamais le basename : depuis le
repo-par-client (RM1887), les basenames sont partagés entre clients (`infra-core` ×6,
`*-core` généralisés). 0 ou >1 match exact = erreur explicite, pas de fallback.

Conséquence vécue du non-respect : `pm-mr.py` (résolution par search + 1er match basename)
a créé une MR sur **le repo d'un autre client** (`calyclay/infra-core` au lieu de
`iprospective/infra-core`) → risque de fuite inter-clients. Bug tracké **RM2219** ;
tant que non livré, vérifier le namespace de toute MR créée par `pm-mr.py`.

## Divers

- L'API renvoie parfois un **corps vide sur succès** → re-GET pour confirmer.
- MR : `detailed_merge_status` est la source fiable (`preparing`→`mergeable`) ;
  `sha: null` + `has_conflicts: true` sur une MR fraîche = la **branche source n'existe
  pas** sur ce projet (symptôme typique d'une MR créée au mauvais endroit).
- Groupes : `/groups/<name>/…` peut mal résoudre — préférer l'ID numérique de groupe aussi.
