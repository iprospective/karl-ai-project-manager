---
bootstrap_template: "002-git-repos"
default_checked: true
title: "Setup : repos git du workspace + remote"
type: infrastructure
priority: high
tags: [bootstrap, git, gitlab]
roi:
  immediate_benefit: 4
  monthly_benefit: 3
estimate:
  difficulty: low
  time_minutes: 30
applicable_when: |
  Le workspace contient du code (au-delà des configs) et n'a pas encore de remote git
  configuré, OU le projet PM a `gitlab.repo: ""` dans son overview.
---

## Contexte

Tout projet code doit avoir un repo git distant pour la sauvegarde, le partage et
l'historique. Convention iProspective : `gitlab:<group>/<project>.git` (alias SSH avec
ProxyJump dans `~/.ssh/config`).

## Critères d'acceptation

- [ ] Le workspace de code (cf. `.mmi-pm/workspace` ou `paths.workspace_link`) est un repo git initialisé
- [ ] `.gitignore` adapté au projet (exclure logs, configs sensibles, build artifacts,
      bundles, node_modules, etc.)
- [ ] Premier commit avec un état propre et fonctionnel
- [ ] Repo distant créé côté GitLab (groupe `iprospective/<sous-groupe>`)
- [ ] Remote `origin` ajouté en utilisant l'alias SSH (ex: `gitlab:iprospective/<P>.git`),
      pas `git@gitlab...`
- [ ] Premier `git push -u origin <branche>` réussi
- [ ] `gitlab.repo` renseigné dans `project/overview.md` du PM
- [ ] Si plusieurs sous-repos (ex: code + modules submodules), tous documentés

## Instructions

1. Se placer dans le workspace de code (résolu depuis `paths.project/workspace` ou
   accessible directement)
2. `git init -b main` si pas déjà fait
3. Rédiger un `.gitignore` adapté
4. Premier commit : `git add . && git commit -m "Initial commit"`
5. Créer le projet GitLab :
   ```bash
   glab api projects --method POST --hostname gitlab.iprospective.fr \
     -f name="<P>" -f path="<P>" -f namespace_id=<ID> -f visibility=private \
     -f default_branch=main
   ```
6. `git remote add origin gitlab:<group>/<P>.git`
7. `git push -u origin main`
8. Mettre à jour `project/overview.md :: gitlab.repo`

## Références

- `~/.ssh/config` (alias SSH `gitlab`, `gogs`, etc.)
- Conventions de groupes GitLab iProspective (ex: namespace_id 109 pour
  `iprospective/prestashop`)
