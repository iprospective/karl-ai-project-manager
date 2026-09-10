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
  distants via un vault déclaré (URI `secret://…` — ou `vaultwarden://…`, forme
  historique — dans la conf, résolu au runtime).

Détails d'usage et conventions : voir le skill `mmi-env-sync`.

## brevo-cleaner/

Purge d'un compte **Brevo** des contacts spam à **nom aléatoire** (vague d'inscriptions
bot). Outil autonome (python) sur le même modèle que `synchro/` : entrypoint
self-localisé, conf par projet gitignorée, secrets lus au runtime depuis la prod.
Suppression conditionnée à 3 critères cumulatifs (nom charabia **ET** absent de la prod
**ET** aucune commande), backup intégral systématique, modes `plan` (dry-run) /
`apply --yes`. Point d'entrée : `brevo-cleaner/brevo_cleaner.py <env> plan|apply`.
Détails : voir `brevo-cleaner/README.md`.

## browser-check/

**Validation NAVIGATEUR** d'une page avant de livrer du front, imposée par NORMS `testing` §7
sur les projets `browser_test: true` (sites publics). Charge une URL dans un Chromium headless
déjà présent en cache, exécute un geste, lit la console et **constate l'effet dans l'interface** ;
sort en `0`/`1`, donc s'écrit tel quel dans un protocole de test. Verdict en logique **pure**
(`lib.js`, testé sans navigateur) séparé de l'observation. Point d'entrée :
`browser-check/browser-check.js --url <URL> [--click …] [--expect-change …]`.
Détails : voir `browser-check/README.md`.
