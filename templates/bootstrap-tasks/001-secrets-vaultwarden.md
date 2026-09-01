---
bootstrap_template: "001-secrets-vaultwarden"
default_checked: true
title: "Setup : items de vault et secrets_source des environnements"
type: infrastructure
priority: high
tags: [bootstrap, secrets, vaultwarden]
roi:
  immediate_benefit: 4
  monthly_benefit: 3
estimate:
  difficulty: low
  time_minutes: 30
applicable_when: |
  Le projet a au moins un environnement déclaré (environments[].secrets_source: null)
  OU des credentials sensibles (clés API, mots de passe BDD, tokens) à manipuler.
---

## Contexte

Tout projet manipulant des credentials sensibles (BDD, API tiers, secret keys, certifs,
SSH keys, etc.) doit les ranger dans un vault plutôt que dans le repo PM ou le
workspace. Référence : `norms/NORMS.md` § « Gestion des secrets — vaults déclarés ».

Le vault par défaut est Vaultwarden ; un projet ou un client peut en déclarer un autre
(axe `secret` du registre providers, cf. RM2662).

## Critères d'acceptation

- [ ] Une collection existe dans le vault du projet pour ses secrets (idéalement
      `<client>-agents` dans l'org `iProspective`)
- [ ] L'user `karl@iprospective.fr` (ou tout autre user d'agents) a un accès **Read only**
      à cette collection
- [ ] Pour chaque environnement déclaré dans `project/environments.md`, un item
      existe et la valeur `secrets_source` du frontmatter est renseignée au format
      `secret://<instance>/<chemin>` (ou `vaultwarden://<org>/<coll>/<item>`)
- [ ] Les items contiennent au minimum les champs : `password`, `notes` (si utile),
      éventuellement des `fields` custom (ex: `host`, `port`, `db_name`, etc.)
- [ ] Test : `./scripts/resolve-secret.sh "<uri>"` retourne bien la valeur

## Instructions

1. Lister les credentials sensibles connus du projet (BDD, API, tokens, certifs…)
2. Créer la collection si elle n'existe pas encore (UI du vault, en tant qu'admin)
3. Inviter et **confirmer** karl@ dans la collection en Read only
4. Créer un item par cluster de secrets (typiquement 1 item par env)
5. Renseigner `secrets_source` dans le frontmatter de chaque environnement de
   `project/environments.md`
6. Tester end-to-end avec `resolve-secret.sh`

## Références

- `norms/NORMS.md` § « Gestion des secrets — vaults déclarés »
- `knowledge/redmine/` (si Redmine impliqué)
- `scripts/unlock-vault.sh [-i <instance>]`, `resolve-secret.sh`, `vault-list.sh`,
  `pm-providers.py resolve secret` (quel vault pour ce projet ?)
