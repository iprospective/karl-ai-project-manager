---
bootstrap_template: "001-secrets-vaultwarden"
default_checked: true
title: "Setup : items Vaultwarden et secrets_source des environnements"
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
SSH keys, etc.) doit les ranger dans Vaultwarden plutôt que dans le repo PM ou le
workspace. Référence : `norms/NORMS.md` § "Gestion des secrets — Vaultwarden".

## Critères d'acceptation

- [ ] Une collection Vaultwarden existe pour les secrets de ce projet (idéalement
      `<client>-agents` dans l'org `iProspective`)
- [ ] L'user `karl@iprospective.fr` (ou tout autre user d'agents) a un accès **Read only**
      à cette collection
- [ ] Pour chaque environnement déclaré dans `project/environments.md`, un item
      Vaultwarden existe et la valeur `secrets_source` du frontmatter est renseignée
      au format `vaultwarden://<org>/<collection>/<item-uuid-or-name>`
- [ ] Les items contiennent au minimum les champs : `password`, `notes` (si utile),
      éventuellement des `fields` custom (ex: `host`, `port`, `db_name`, etc.)
- [ ] Test : `./scripts/resolve-secret.sh "vaultwarden://..."` retourne bien la valeur

## Instructions

1. Lister les credentials sensibles connus du projet (BDD, API, tokens, certifs…)
2. Créer la collection si elle n'existe pas encore (UI Vaultwarden, en tant qu'admin)
3. Inviter et **confirmer** karl@ dans la collection en Read only
4. Créer un item Vaultwarden par cluster de secrets (typiquement 1 item par env)
5. Renseigner `secrets_source` dans le frontmatter de chaque environnement de
   `project/environments.md`
6. Tester end-to-end avec `resolve-secret.sh`

## Références

- `norms/NORMS.md` § "Gestion des secrets — Vaultwarden"
- `knowledge/redmine/` (si Redmine impliqué)
- `scripts/unlock-vault.sh`, `resolve-secret.sh`, `vault-list.sh`
