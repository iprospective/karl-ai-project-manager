---
type: index
created: 2026-06-08
---

# tools/ — outillage PM (non-python)

Outils versionnés et distribués avec le repo PM, hors des scripts python de `scripts/`.

## synchro/

Framework de **synchronisation d'environnement** prod → dev/test (BDD + fichiers) avec
adaptations de sécurité (mails, paiements, sync, domaine). Piloté par le skill
[`mmi-env-sync`](../skills/mmi-env-sync/). Point d'entrée : `synchro/sync.sh <env>`.

- `sync.sh` — orchestrateur (self-localisé ; pas de chemin en dur vers ce dossier).
- `lib/<type>.sh` — logique par type de site (`presta`, `dolibarr`, `wordpress`…).
- `environments/<env>.conf` — **gitignoré** : confs machine-spécifiques (db, alias SSH,
  domaine). **Aucun secret en clair** : MySQL admin local via `~/.my.cnf`, secrets
  distants via Vaultwarden (`vaultwarden://` dans la conf, résolu au runtime).

Détails d'usage et conventions : voir le skill `mmi-env-sync`.
