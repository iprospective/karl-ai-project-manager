---
name: mmi-zabbix
description: Interroge et pilote Zabbix (monitoring du parc) depuis le PM, en déléguant à atlas — aucun secret Zabbix côté PM. Lecture (état hôte, items + dernières valeurs, problèmes actifs, LLD) et actions sûres (ack, LLD « execute now »). Usage : "/mmi-zabbix host srv3", ou langage naturel "dernières valeurs CPU de srv3 via Zabbix", "problèmes actifs sur le parc", "acquitte l'événement Zabbix 12345".
allowed-tools: Bash, Read
---

# Skill : mmi-zabbix

Façade **orchestrateur** : le PM ne parle jamais à Zabbix en direct (pas de token, pas de
JSON-RPC côté PM — frontière D3, RM2421). Tout passe par **atlas**, seul détenteur de l'accès :
canal SSH forced-command (RM2516) → catalogue atlas (RM2496) → client Zabbix (RM2454).

## Quand déclencher

- "état Zabbix de <hôte>", "dernières valeurs <métrique> de <hôte>", "items de <hôte>"
- "problèmes actifs (sur le parc / sur <hôte>)", "règles LLD de <hôte>"
- "acquitte l'événement Zabbix <id>", "relance la découverte LLD <ruleid>"
- `/mmi-zabbix <verbe> …`

## Invocation

Depuis la racine du repo code (le script est dans le skill) :

```bash
skills/mmi-zabbix/zabbix.sh ops                       # liste des ops zbx-*
skills/mmi-zabbix/zabbix.sh host <fqdn>               # état structuré d'un hôte
skills/mmi-zabbix/zabbix.sh items <fqdn>              # items + dernières valeurs
skills/mmi-zabbix/zabbix.sh problems [fqdn]           # problèmes actifs (hôte optionnel)
skills/mmi-zabbix/zabbix.sh lld <fqdn>                # règles de découverte
skills/mmi-zabbix/zabbix.sh ack <eventid> "<message>" [--dry-run]   # acquitter (action=6)
skills/mmi-zabbix/zabbix.sh lld-run <ruleid> [--dry-run]            # LLD « execute now »
```

- Les hôtes sont des **FQDN** (`srv3.iprospective.net`) — atlas résout le nom exact.
- Sortie = JSON du cœur atlas : `{"ok": true, "stdout": "<JSON zbx structuré>", …}`. Parser
  `stdout` (re-JSON) pour la donnée métier.
- **Toujours `--dry-run` d'abord** sur une action (`ack`/`lld-run`) pour vérifier l'appel prévu.

## Garde-fous (ne pas contourner)

- **Verbes read-only + actions P1 uniquement** via ce canal. Les actions **P2** (`disable`
  item/trigger, `link-template`) sont **refusées par le cœur atlas** (droit `atlas-orch` zbx-only
  P1) — c'est volontaire. Si un besoin légitime apparaît, ça se décide côté atlas (élargir le
  droit + `op_max_tier`), pas ici.
- `ack` reste en `action=6` (acquittement + message, **jamais** le bit *close* — garde
  `manual_close`, cf. `knowledge/zabbix/api.md`).

## Traçabilité (rôle orchestrateur)

Après une **action** (pas la simple lecture), **append au `.log.md`** du ticket courant : le verbe,
la cible, et le résultat (via `mmi-pm-task-comment` ou l'append direct). Le pilotage d'atlas doit
laisser une trace côté PM en plus de l'audit-trail d'atlas.

## Voir aussi

- Canal : RM2516 (`orch_runner.py` côté atlas) · Ops : RM2496 · Client : RM2454
- Architecture (frontière 3 rôles) : RM2421 · Savoir Zabbix : `knowledge/zabbix/api.md`
