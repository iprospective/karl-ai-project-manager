# Travailler le PM en CLI, sans cockpit

- **Ticket** : RM2500 (T4 — « Mode CLI sans cockpit »)
- **Public** : un dev qui veut boucler un ticket avec les seuls scripts `pm-*`,
  sans le cockpit web (`deploy/karl-agent/`), sans tmux, sans vhost.

Le PM est déjà **découplé du cockpit par conception** : le cockpit supervise/expose
les sessions, mais n'est requis par aucune commande. Ce document décrit le **profil
opt-in** qui coupe le seul couplage automatique restant (l'env de session), et la
surface CLI minimale pour travailler un ticket.

> Ce profil ne change **aucun comportement par défaut**. Sans l'opt-in décrit ici,
> le PM se comporte exactement comme avant.

## Prérequis

- **Python 3 + PyYAML** (`python3 -c 'import yaml'`). C'est tout ce dont dépendent
  les scripts `pm-*`.
- **`.env`** rempli à la racine du repo (`cp .env.example .env`) : token GitLab,
  clé API Redmine, `PROJECTS_PATH`… (cf. `README.md` § Installation).
- Un workspace projet relié au PM (symlink `.mmi-pm`) **ou** travailler depuis le
  repo PM. La résolution passe par `pm.config.yml` / `scripts/pm_paths.py`.

Aucun besoin de cockpit, de service `karl-agent`, de tmux ni de vhost pour ce qui suit.

## Couper l'env de session automatique (`auto_session: false`)

Le **seul** point de contact statut → env-de-session est le hook `env_session_hook()`
de `scripts/pm-task-status-update.py` : sur une transition vers `en_cours` il crée
l'env de session (`pm-env-session create` — worktree, éventuel clone BDD, vhost),
sur `ferme` il le démonte. Ce hook est **best-effort, jamais bloquant** : même en
échec il n'empêche pas la transition de statut.

Pour un profil CLI-seul, on le débraye via la config. Le drapeau est lu ici :

```
scripts/pm-task-status-update.py:197
    if not env_cfg.get("auto_session", True):
        return          # court-circuit AVANT toute création d'env / vhost
```

et le hook n'est de toute façon invoqué que sur `en_cours` / `ferme`
(`pm-task-status-update.py:814`). Avec `auto_session: false`, **aucune** tentative
d'env-session ni de vhost n'est faite sur ces transitions.

Pose le drapeau dans **`pm.config.local.yml`** (surcharge gitignorée de
`pm.config.yml`, ne touche pas au canonique versionné) à la racine du repo :

```yaml
# pm.config.local.yml — profil dev CLI-seul
env_runtime:
  auto_session: false
```

Le défaut versionné (`pm.config.yml :: env_runtime.auto_session: true`) reste
inchangé : c'est bien un **opt-in par machine/dev**, pas une bascule globale.

## Surface CLI pour boucler un ticket

Tous ces scripts vivent dans `scripts/` et s'appellent en `python3 scripts/<nom>.py`
(ou via l'alias `mmi-pm` / les skills `mmi-pm-*`). `--help` sur chacun ; la
`norms/CHEATSHEET.md` en donne une vue d'ensemble à lire une fois par session.

| Étape | Commande |
|---|---|
| Voir ce qui reste à faire | `pm-task-list.py` |
| Détail d'un ticket | `pm-task-show.py <id>` |
| Prendre le ticket (→ `en_cours`, auto-assignation) | `pm-task-take.py <id>` |
| Démarrer la branche de travail | `pm-branch-start.py <id>` |
| Commenter (Redmine + `.log.md`) | `pm-task-comment.py <id> --note '…'` |
| Changer de statut (source unique des transitions) | `pm-task-status-update.py <id> <statut>` |
| Lier des tickets (relates/depends/blocks) | `pm-task-link.py add <a> <b> --type …` |
| Comprendre un blocage de transition | `pm-task-blockers.py <id>` |
| Ouvrir la merge request | `pm-mr.py …` |
| Resynchroniser depuis Redmine | `pm-task-sync.py <id>` |
| Récap d'avancement de la session | `pm-session-status.py` |

Flux nominal : `pm-task-take` → `pm-branch-start` → travail + `pm-task-comment` →
`pm-task-status-update` (livraison) → `pm-mr`. Le worklog de session
(`pm-session-status`) est alimenté automatiquement par les scripts qui modifient
l'état d'un ticket ; aucun cockpit n'est nécessaire pour le tenir à jour.

## Exposer les skills `mmi-pm-*` (optionnel)

Pour piloter ces mêmes opérations en langage naturel depuis Claude Code, les skills
`mmi-pm-*` du repo (`skills/`) se branchent dans le dossier skills utilisateur :

```bash
python3 scripts/pm-skills-sync.py --dry-run   # montre ce qui serait fait
python3 scripts/pm-skills-sync.py             # crée les symlinks → ~/.claude/skills
```

`pm-skills-sync.py` **symlinke** les skills PM dans `~/.claude/skills` (cible
configurable via `--target`, `--dry-run` pour un aperçu sans écriture, `--prune`
pour retirer les liens orphelins). C'est un confort : la surface CLI ci-dessus
fonctionne sans les skills.

## Ce dont on n'a PAS besoin en mode CLI-seul

- Pas de **cockpit web** ni de service `karl-agent`.
- Pas de **tmux** ni de session d'agent supervisée.
- Pas de **vhost** ni d'env de session (`pm-env-session`) — coupés par
  `auto_session: false`. Un env de session reste créable **à la main** au besoin
  (`pm-env-session.py create <id> <ws>`), ce n'est simplement plus automatique.
