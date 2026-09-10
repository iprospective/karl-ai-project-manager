> 📂 **Module `session-tooling-pratique` — quand lire ceci :** je cherche si un geste a son outil ou s'il reste manuel · je veux l'invocation exacte d'un `pm-*` sans relancer `--help`.
> **Outils :** tous les `pm-*` · **Préchargé par :** *(personne — ouvert à la demande)*.

Détail sorti de `session-tooling` (RM3037) pour tenir le budget de contexte : la **règle** — tout ce qui
change un état passe par l'outil PM, un trou se comble en créant le script — reste dans le module
préchargé et dans le tripwire #1. Ce qui suit est de la **consultation**.

### Couverture actuelle (à compléter au fil des trous identifiés)

| Domaine | Opération | Outil canonique |
|---|---|---|
| Tâche | créer | `pm-task-add.py` · `mmi-pm-task-add` (`--porcelain` = id nu sur stdout) |
| Tâche | changer le statut | `pm-task-status-update.py` · `mmi-pm-task-status-update` |
| Tâche | commenter | `pm-task-comment.py` · `mmi-pm-task-comment` |
| Tâche | lier (relates/depends/blocks) | `pm-task-link.py` · `mmi-pm-task-link` |
| Tâche | **déplacer vers un autre projet PM** (fiche + `.log` + `.reporting`, et `project_id` Redmine vérifié par relecture) | `pm-task-move.py <id> --to <client>/<projet>` (RM2866) |
| Tâche | description / checklist | `pm-task-description-update.py` |
| Tâche | estimation (CF prévisionnels) | `pm-task-metrics-push.py --estimate` |
| Tâche | mesure temps/tokens (hook) | `pm-task-tick.py` |
| Tâche | report conso → Redmine (time_entries + CF17) | `pm-task-report.py` |
| Donnée PM | commit+push des écritures de scripts | *(automatique — `pm_git.autocommit`, RM1834 ; **silencieux si ça passe**, RM2440 ; `--no-commit` pour débrayer)* |
| Donnée PM | **rattrapage** de ce qui traîne (édits libres : fiches, `.log.md`, CDC…) | *(automatique — chaque `pm_git.autocommit` d'un script embarque, dans un commit `pm(rattrapage): …` séparé, les fichiers non commités depuis **plus d'1 h** ; ni timer ni process dédié, RM3013 ; `git.sweep: false` / `git.sweep_after_min` ; journalisé catégorie `pm`)* |
| Repo | protection de branches (code **ou** core) | `pm-protect.py` (`--repo` · `--all-cores`) |
| Instance | pont d'onboarding des workspaces (`AGENTS.md` + `CLAUDE.md`) | `pm-workspace-bridge.py` (nu = contrôle · `--install` · `--update`, RM1892) |
| Repo | promouvoir intégration → prod | `pm-promote.py` — ⚠ **transition** (RM2440), hors flux nominal |
| Tâche | démarrer la branche de ticket (+ CF GIT Branche) | `pm-branch-start.py` (`--worktree --print-cd` = chemin nu à `cd`) |
| Tâche | se (re)placer dans le worktree du ticket | `pm-task-cd.py` — `cd "$(pm-task-cd.py <id>)"` (RM2240) |
| Projet | cohérence des paires cross-projet (used_by/provided, implements) | `pm-doctor.py` |
| Tâche | sync depuis Redmine | `pm-task-sync.py` · `mmi-pm-task-sync` |
| Tâche | lister / afficher | `pm-task-list.py`, `pm-task-show.py` |
| Tâche | **reprendre sans sa session** (séances, prochaine étape notée, demandes retrouvées, état constaté du code) | `pm-task-brief.py <id> --reprise` (RM2998) |
| Contact | **annuaire de personnes** (ajout, fusion, recherche par adresse, migration) | `pm-contact.py` (RM2703) |
| Contact | rattacher à un client (rôle, titre) | `pm-client-contact.py` |
| Projet / client | créer / bootstrap | `pm-project-new.py`, `pm-project-bootstrap.py`, `pm-client-new.py` |
| Ticket Redmine (bas niveau) | note / fetch / tag IA / config | `redmine-post-note.py`, `redmine-fetch-*.py`, `redmine-tag-ia.py`, `redmine-config-check.py` |
| Session | worklog d'avancement | `pm-session-status.py` · `mmi-pm-session-status` |
| Session | **archiver les transcripts** (+ `history.jsonl`, worklogs) et surveiller que ça tourne | `pm-sessions-archive.py` (`--check`, `--install-timer`) (RM2997) |
| Session | **événement notable** (secret exposé, refus, garde-fou, outillage en défaut, décision bloquante) | `pm-session-status.py notify` |
| Session | **demande du demandeur** (avant même de savoir si elle sera ticketée) | `pm-session-status.py request` |
| Session → tâche | **consigner les décisions** (questions tranchées / restées sans réponse) dans le journal du ticket | `pm-decisions.py persist <id>` |
| **Branches / repos / submodules** | créer la branche d'un ticket (+ CF GIT Branche) | `pm-branch-start.py` (livré RM1923 ; `--worktree`, `--take`) |
| **Commit + push conventionné** | message conventionné, push immédiat, base de version | **⚠ trou — pas de script dédié** : geste manuel encadré (cf. § « Commit + push systématique ») |

### Idiomes fréquents (évite de relancer `--help` à chaque session)

- **Contenu long / multi-ligne via stdin** : `pm-task-comment <id> --note - < note.md`,
  `redmine-post-note <id> --note -`, `pm-task-add --description -` (ou
  `--description-file <path>`), `pm-task-description-update <id> --set-from-file <path>`.
  Passer par stdin/fichier plutôt qu'un argument quoté évite AUSSI la protection
  Bash « newline + `#` » de Claude Code (validation à répétition sur les arguments
  multi-lignes contenant un dièse).
- **Transitions valides depuis le statut courant** : `pm-task-status-update <id> --list-next`
  (au lieu de deviner le flow d'états).
- **Auto-assignation** : `en_cours` auto-assigne au porteur (`--assign-to me` implicite) ;
  `--assign-to <id|me|author>` pour forcer, `--no-assign` pour débrayer.
- **Détection de projet** : si la détection cwd échoue ou est ambiguë,
  `--project entity/project` explicite (`pm-task-add`, `pm-task-list`, …).
- **Répétition sans risque** : `--dry-run` sur `pm-task-add`, `pm-task-status-update`,
  `pm-task-sync` — voir le diff avant d'écrire.
- **Script lancé depuis un worktree sans `.env`** : préfixer
  `PM_CORE_DIR=<racine du repo PM actif>` (sinon « ERREUR : aucun .env trouvé »).
