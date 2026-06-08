---
type: index
created: 2026-06-07
---

# Skills PM — distribués à toutes les instances

Ce dossier héberge les **skills Claude Code** (packages `SKILL.md`) qui font partie de
l'outillage PM et doivent être **disponibles sur toutes les instances** qui clonent ce
repo (`ai-project-management`). C'est le canal de distribution cross-instance des skills,
distinct de :

- `~/.claude/skills/` (repo perso `claude-skills`) — skills **personnels**, indépendants de PM.
- `~/.agents/skills/` (repo `agents-skills`) — skills agents partagés, hors périmètre PM.

## Pourquoi un mécanisme de symlink

Claude Code n'auto-découvre les skills que depuis `~/.claude/skills/`, le `.claude/skills/`
d'un projet, ou les plugins. Un `SKILL.md` posé ici n'est donc **pas invocable** tel quel :
chaque instance doit l'**exposer** via un symlink dans `~/.claude/skills/`. C'est le rôle de
`scripts/pm-skills-sync.py` (même pattern que les symlinks `~/.claude/skills/X → ~/.agents/skills/X`
déjà utilisés pour les skills agents).

## Installation sur une instance

```bash
python3 scripts/pm-skills-sync.py          # crée/rafraîchit les symlinks
python3 scripts/pm-skills-sync.py --dry-run # montre sans rien changer
python3 scripts/pm-skills-sync.py --prune   # retire en plus les symlinks devenus orphelins
```

À lancer **après chaque `git pull`** qui ajoute/supprime un skill (ou une fois au setup
de l'instance). Idempotent : ne touche pas aux skills perso, ne supprime jamais un vrai
dossier (collision de nom → averti et ignoré).

## Convention

- Un sous-dossier par skill, nommé exactement comme le skill (`name:` du frontmatter).
- Chaque sous-dossier contient au minimum `SKILL.md` (frontmatter `name` + `description`).
- Réserver ce dossier aux skills **réellement transverses au PM** (ex: opérer le PM,
  outillage dev partagé). Les skills d'un domaine spécifique (sécurité, etc.) vivent dans
  leur propre repo.

## Skills présents

**Opération du PM** (wrappers des scripts `pm-*.py` / `karl-*.py`) :

- [`mmi-pm-task-add`](./mmi-pm-task-add/), [`mmi-pm-task-list`](./mmi-pm-task-list/),
  [`mmi-pm-task-show`](./mmi-pm-task-show/), [`mmi-pm-task-status-update`](./mmi-pm-task-status-update/),
  [`mmi-pm-task-comment`](./mmi-pm-task-comment/), [`mmi-pm-task-link`](./mmi-pm-task-link/),
  [`mmi-pm-task-sync`](./mmi-pm-task-sync/) — cycle de vie des tâches.
- [`mmi-pm-project-new`](./mmi-pm-project-new/), [`mmi-pm-project-bootstrap-replay`](./mmi-pm-project-bootstrap-replay/),
  [`mmi-pm-client-new`](./mmi-pm-client-new/) — création projets/clients.
- [`mmi-pm-karl-mail-send`](./mmi-pm-karl-mail-send/), [`mmi-pm-karl-sms-private-send`](./mmi-pm-karl-sms-private-send/) —
  notifications de karl.
- [`mmi-pm-session-status`](./mmi-pm-session-status/) — suivi d'avancement **par session**
  (worklog local keyé par `$CLAUDE_CODE_SESSION_ID`) ; répond cheap à « il reste quoi à
  faire dans cette session ». Volet déclaratif de RM1875.

**Outillage dev partagé** :

- [`mmi-env-sync`](./mmi-env-sync/) — synchroniser un environnement de dev/test depuis la
  prod (BDD + fichiers) via le framework `tools/synchro/`, avec adaptations de sécurité.
