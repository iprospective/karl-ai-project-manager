# Worktrees : dépôt central ou dépôt de chaque utilisateur

- **Ticket** : RM3209 — cas d'origine : une équipe dont chaque dev a son dépôt, envs servis par vhosts.
- **Public** : l'administrateur d'une instance PM, puis chaque dev.

## Les trois réglages

| Réglage | Qui le pose | Valeurs | Défaut |
|---|---|---|---|
| `git.worktree_source` | admin, `pm.config.local.yml` | `central` : `<workspace>/repos/<repo>.git` · `per_user` : le dépôt du dev | `central` |
| `git.envs_layout` | admin, `pm.config.local.yml` | `project` : `<workspace>/envs/<env>` · `user` : `<workspace>/envs/<utilisateur>/<env>` | `project` |
| dossier des dépôts | chaque dev, `PM_REPOS_DIR` dans `<core>/var/users/<user>/.env` | un dossier ; le dépôt est `<dossier>/<repo>` | `~/repos` |

Les deux premiers sont des réglages **d'instance** : ils ne se lisent que dans les fichiers de configuration,
jamais dans l'environnement (sinon chacun pourrait les contourner), et le cockpit les réserve à l'admin. Une valeur
inconnue est refusée.

```yaml
# pm.config.local.yml — exemple
git:
  worktree_source: per_user
  envs_layout: user
```

## Ce que ça change pour un dev

- Son dépôt vit dans son dossier de dépôts : `~/repos/site`.
- `pm-branch-start <id> --worktree`, lancé **depuis ce dépôt**, crée l'env `<workspace>/envs/<dev>/site-rm<id>`.
  Lancé depuis le dépôt d'un autre, il refuse en nommant les deux chemins.
- `pm-env-session create` part du même dépôt ; s'il manque, le message dit où le cloner.
- `pm-env-init` ne crée pas de dépôt partagé en `per_user`.

Prérequis de droits : `<workspace>/envs/` en `2770`, groupe `pm` (modèle `pm-perms`), créé une fois par l'admin
quand la racine du workspace n'est écrite que par root.

## Déplacer les envs existants

`mmi-pm env-relocate --plan plan.yml` — le plan se relit avant exécution (docstring de `scripts/pm-env-relocate.py`
pour le format complet) :

```yaml
workspace: /srv/site
repo: site
compat_links: [AGENTS.md, data_dev, agent_config]      # liens relatifs qui sortent de l'env
references: [/etc/apache2/sites-enabled/site.conf, /etc/php/*/fpm/pool.d/*.conf, /srv/site/*.sh]
envs:
  - {from: /srv/site/alice2, name: site-2, owner: alice}
```

Déroulé conseillé :

1. `mmi-pm env-relocate --plan plan.yml --dry-run` — contrôle préalable, destinations, diffs des références ;
2. snapshot ZFS du conteneur **sur l'hôte** ;
3. `sudo mmi-pm env-relocate --plan plan.yml --snapshot "<nom>"` (ajouter `--reload` pour recharger Apache et
   PHP-FPM), en commençant par un env partagé ;
4. vérifier les vhosts ; en cas de problème : `sudo mmi-pm env-relocate --undo <journal>`.

Ce que l'outil préserve : commit courant, fichiers modifiés, non suivis et ignorés (l'arbre de travail n'est pas
réécrit), branches locales et stashes (importés en `relocate/<env>/…` dans le dépôt du propriétaire). L'ancien
`.git` est conservé à côté de l'env tant qu'on ne le supprime pas.
