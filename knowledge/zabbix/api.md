---
type: knowledge
product: zabbix
created: 2026-07-10
---

# Zabbix — API JSON-RPC : accès et pièges

Serveur du parc : machine `obs`, frontend `https://zabbix.iprospective.fr`, endpoint
`/api_jsonrpc.php`. Token : `.env` du repo PM (`ZABBIX_API_TOKEN`), header
`Authorization: Bearer <token>`.

## ⚠ Piège n°1 : `search` = faux négatifs SILENCIEUX

`trigger.get`/`item.get` avec `search:{...}` (+ `searchWildcardsEnabled`) peut renvoyer
**0 résultat alors que les objets existent** — vécu 2026-07-10 : `trigger.get
search={"description":"memory"}` → 0, alors que « High memory utilization » existait sur
des dizaines d'hôtes (et était en PROBLÈME). Aucun message d'erreur : le résultat vide a
l'air légitime.

**Règle : pour tout inventaire fiable, récupérer LARGE (par `hostids`, ou `filter:{"value":1}`
pour les problèmes) SANS `search`, et filtrer côté client (Python).** Cf. règle transverse
de l'[INDEX](../INDEX.md) — même famille de piège que le search GitLab.

## Piège n°2 : hôtes en FQDN

Les `host` techniques sont des FQDN (`obs.iprospective.net`, `elrond.abatk.com`…), pas les
noms courts. Un `filter:{"host":["obs"]}` ne matche rien ; un `search` partiel matche
n'importe quoi (le 1er venu). Résoudre le FQDN exact d'abord (`host.get` + filtre client).

## Triggers : états figés et fermeture

- **Un trigger ne se réévalue pas pendant un nodata** : si l'item source cesse d'émettre,
  le trigger reste GELÉ dans son dernier état (vécu : « High memory utilization » resté
  en PROBLÈME **~700 jours** sur elrond car l'item était en nodata ~693 j). Une alerte
  très ancienne = suspecter un trou de données, pas une vraie condition.
- **`manual_close=0`** (défaut des templates Linux) ⇒ `event.acknowledge` avec
  `action` incluant le bit *close* (1) est REFUSÉ. Le flag est défini au niveau du
  **template partagé** : l'activer impacte tous les hôtes qui l'utilisent. Alternative
  sûre : acquitter + message (`action:6` = acknowledge(2)+message(4)).
- `event.acknowledge` : `action` est un **bitmask** — 1=close, 2=acknowledge, 4=message,
  8=sévérité… Additionner les opérations voulues.

## Items dépendants

`vm.memory.utilization` (type 18 = dependent) est calculé de `vm.memory.size[pavailable]`
(`100 − pavailable`) dans le template Linux du parc : corriger/aliaser la **source**
suffit, l'item dépendant suit. Vérifier la chaîne avant de « corriger » l'aval.

## Voir aussi

- Doc parc mémoire ZFS/LXC : `.mmi-pm/docs/zabbix-zfs-arc-memoire.md` (workspace
  iprospective/infra) — alias ARC hôtes (RM2124) + alias LXC (RM2172).
