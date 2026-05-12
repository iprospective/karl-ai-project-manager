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

## Architecture proposée (Option C — recommandée)

**MD reste source de vérité**, une DB indexée (SQLite) sert de cache pour les requêtes :

```
Browser (HTMX) ─→ FastAPI ─→ SQLite (index, read-only)
                       └──→ MD files (writes)
                              ▲
                              │ watchdog
                       Indexer (daemon)
                              ▲
                              │ lecture/écriture
                       Agents (Claude)
```

**Pourquoi** : pas de sync bidirectionnel (le cauchemar), git reste source d'historique,
l'indexer se reconstruit en 30s depuis les MD.

## Choix à trancher avant code

- [ ] **Stack tech** : FastAPI + HTMX + Alpine + Tailwind (recommandé) vs autre (Node, PHP, Go)
- [ ] **Localisation** : même serveur que les agents vs service séparé (impact accès filesystem)
- [ ] **Auth** : public local / restriction IP / OAuth GitLab
- [ ] **Granularité supervision live** : tail des `.log.md` suffit, ou les agents doivent émettre des événements dédiés (webhook, message queue) ?
- [ ] **Métriques** : SQLite + Chart.js (simple, intégré) vs Prometheus + Grafana (robuste, externe)

## Phasage proposé (ordre par ROI)

| Phase | Effort estimé | Valeur immédiate |
|---|---|---|
| 0. CLI dashboard (terminal, lit MD, top ROI, statut global) | 2-3 h | 80 % de la valeur sans UI |
| 1. Indexer + UI lecture web | 2-3 j | Browse, filtres, recherche |
| 2. UI édition (formulaires → génère MD) | 2-3 j | Création/édition sans MD brut |
| 3. Supervision live (WebSocket + tail `.log.md`) | 1-2 j | Vue temps réel des agents |
| 4. Métriques historiques (tokens, cycle time, ROI réalisé vs estimé) | 1-2 j | Pilotage long terme |

## Critères d'acceptation

- Un humain peut superviser l'activité de tous les agents sans ouvrir un terminal
- La création/édition d'une tâche depuis l'UI génère un MD valide (passe le validator)
- La DB d'index est entièrement reconstructible depuis les MD (rien d'unique en DB)
- La préservation des 3 critères Redmine (cf [TODO 001](001-redmine-value-criteria.md))
  est explicitement vérifiée avant chaque livraison de phase

## Journal

- **2026-05-12** : TODO créée. Discussion architecture menée — Option C (MD source + DB index) retenue comme recommandation. Choix de stack/auth/localisation/supervision encore ouverts.
