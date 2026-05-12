# TODO 002 — Interface de gestion + supervision des agents

| | |
|---|---|
| **Statut** | `pending` |
| **Priorité** | `#priority:high` |
| **Tags** | `#user-request` `#agents` `#meta` |
| **Origine** | Demande user — 2026-05-12 |
| **Créé** | 2026-05-12 |

## Contexte

Le système est fonctionnel en v1.5.0 (normes, hiérarchie, agents, validator).
Prochain palier : disposer d'une **interface humaine** pour superviser, créer,
suivre — sans devoir éditer les MD à la main pour chaque opération.

Deux briques liées :
1. **Interface de gestion** : browse + édition (alternative aux éditeurs MD bruts)
2. **Supervision graphique** : ce que font les agents en temps réel, métriques

## Architecture retenue (Option C — décidée 2026-05-12)

**MD reste source de vérité**, une DB indexée (SQLite) sert de cache pour les requêtes :

```
Browser (HTMX + Twig) ─→ Symfony ─→ SQLite (index, read-only)
                              └──→ MD files (writes)
                                     ▲
                                     │ watchdog (Symfony Messenger ou daemon dédié)
                              Indexer
                                     ▲
                                     │ lecture/écriture
                              Agents (Claude)
                                     │
                                     ▼
                            Mercure Hub ─→ Browser (SSE pour supervision live)
```

**Pourquoi** : pas de sync bidirectionnel (le cauchemar), git reste source d'historique,
l'indexer se reconstruit en 30 s depuis les MD.

## Choix actés (2026-05-12)

| Décision | Choix retenu | Note |
|---|---|---|
| **Stack tech** | Symfony + Twig + HTMX + Alpine + Tailwind | Auth Security bundle, Mercure pour SSE, Doctrine ORM pour la SQLite |
| **Localisation** | Conteneur LXC `dev` existant, ZFS partagé | Accès direct aux MD via mount/bind, pas de sync réseau |
| **Auth** | Locale (login/password) via Security bundle | Hash bcrypt, comptes en SQLite |
| **Supervision live** | Phase 1 : tail des `.log.md` ; Phase 2 : événements structurés | Tail rapide à livrer, événements ajoutés quand le besoin émerge |
| **Métriques** *(reportée)* | À trancher en phase 4 | SQLite + Chart.js vs Prometheus + Grafana |

## Phasage proposé (ordre par ROI)

| Phase | Statut | Effort estimé | Valeur immédiate |
|---|---|---|---|
| 0. CLI dashboard (terminal, lit MD, top ROI, statut global) | ✅ livré 2026-05-12 | 2-3 h | `scripts/pm-dashboard.py` |
| 1. Bootstrap Symfony + indexer + UI lecture web | à faire | 3-4 j | Browse, filtres, recherche |
| 2. UI édition (formulaires Twig → génère MD via service) | à faire | 2-3 j | Création/édition sans MD brut |
| 3. Supervision live (Mercure + tail `.log.md`) | à faire | 1-2 j | Vue temps réel des agents |
| 4. Métriques historiques (tokens, cycle time, ROI réalisé vs estimé) | à faire | 1-2 j | Pilotage long terme |

### Bootstrap Symfony (phase 1) — détail technique

- `composer create-project symfony/skeleton` + `webapp` recipe (Twig, Doctrine, Security, Mercure)
- Doctrine configuré sur SQLite (`var/data.db`)
- Entités initiales : `User`, `Client`, `Project`, `Task` (mappées sur les MD)
- Service `MarkdownIndexer` (lit `$PROJECTS_PATH`, alimente Doctrine via watchdog ou commande `php bin/console pm:index`)
- Service `MarkdownWriter` (écrit les MD depuis les formulaires, valide via `scripts/validate-task.py`)
- Security : provider local en base, `make:user`, login/logout, role hiérarchique
- HTMX + Alpine + Tailwind chargés via AssetMapper (pas de Node requis)

## Critères d'acceptation

- Un humain peut superviser l'activité de tous les agents sans ouvrir un terminal
- La création/édition d'une tâche depuis l'UI génère un MD valide (passe le validator)
- La DB d'index est entièrement reconstructible depuis les MD (rien d'unique en DB)
- La préservation des 3 critères Redmine (cf [TODO 001](001-redmine-value-criteria.md))
  est explicitement vérifiée avant chaque livraison de phase

## Journal

- **2026-05-12** : TODO créée. Discussion architecture menée — Option C (MD source + DB index) retenue comme recommandation. Choix de stack/auth/localisation/supervision encore ouverts.
- **2026-05-12** : Stack tranchée — Symfony + Twig + HTMX + SQLite, conteneur LXC `dev` existant, auth locale, supervision live phase 1 = tail `.log.md`, phase 2 = événements structurés. Choix métriques reporté à la phase 4.
- **2026-05-12** : Phase 0 livrée — `scripts/pm-dashboard.py`. Affiche statuts par projet, top ROI, en cours, à tester, à corriger, activité récente. `rich` si dispo, fallback ASCII. Filtres `--client`, `--top`, `--activity`.
