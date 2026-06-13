> 📂 **Module `session-tooling` — quand lire ceci :** je cherche quel outil PM utiliser pour une opération touchant l'état d'une tâche/branche/repo/Redmine.
> **Outils :** tous les `pm-*` · **Préchargé par :** tous.

## Outillage obligatoire en session PM — v1.35.0

En **session PM** (workspace PM-tracké via `.mmi-pm`, ou travail dans le repo PM), toute
opération touchant à l'**état des tâches, aux branches git, aux repos/submodules ou aux
tickets Redmine** passe par les **skills/scripts PM dédiés** — **jamais à la main**. C'est
ce qui garantit la cohérence Redmine ↔ MD ↔ worklog de session et l'application des
couplages NORMS (auto-assignation, notes, `status_history`, logs, filigrane IA, temps/tokens).

**Règle anti-trou** : si une opération de cette nature a un outil, l'utiliser ; si elle n'en
a pas, c'est un **trou d'outillage à combler** (créer le script/skill) — pas une exception à
faire à la main. En particulier, toute opération qui **amende l'état d'une tâche** est
branchée derrière `pm-task-status-update.py` (**source unique des transitions**), qui propage
Redmine + MD + log + worklog de session. Le worklog de session (`pm-session-status.py`) est
alimenté **automatiquement** par les scripts qui modifient l'état des tâches (via
`pm_session_hook.py`) ; cf. RM1875.

### Couverture actuelle (à compléter au fil des trous identifiés)

| Domaine | Opération | Outil canonique |
|---|---|---|
| Tâche | créer | `pm-task-add.py` · `mmi-pm-task-add` |
| Tâche | changer le statut | `pm-task-status-update.py` · `mmi-pm-task-status-update` |
| Tâche | commenter | `pm-task-comment.py` · `mmi-pm-task-comment` |
| Tâche | lier (relates/depends/blocks) | `pm-task-link.py` · `mmi-pm-task-link` |
| Tâche | description / checklist | `pm-task-description-update.py` |
| Tâche | estimation (CF prévisionnels) | `pm-task-metrics-push.py --estimate` |
| Tâche | mesure temps/tokens (hook) | `pm-task-tick.py` |
| Tâche | report conso → Redmine (time_entries + CF17) | `pm-task-report.py` |
| Donnée PM | commit+push des écritures de scripts | *(automatique — `pm_git.autocommit`, RM1834 ; `--no-commit` pour débrayer)* |
| Tâche | démarrer la branche de ticket (+ CF GIT Branche) | `pm-branch-start.py` |
| Projet | cohérence des paires cross-projet (used_by/provided, implements) | `pm-doctor.py` |
| Tâche | sync depuis Redmine | `pm-task-sync.py` · `mmi-pm-task-sync` |
| Tâche | lister / afficher | `pm-task-list.py`, `pm-task-show.py` |
| Projet / client | créer / bootstrap | `pm-project-new.py`, `pm-project-bootstrap.py`, `pm-client-new.py` |
| Ticket Redmine (bas niveau) | note / fetch / tag IA / config | `redmine-post-note.py`, `redmine-fetch-*.py`, `redmine-tag-ia.py`, `redmine-config-check.py` |
| Session | worklog d'avancement | `pm-session-status.py` · `mmi-pm-session-status` |
| **Branches / repos / submodules** | créer branche par ticket, commit+push conventionné, base de version | **⚠ trou — aucun outil dédié** (cf. § « Branche de travail par ticket », § « Commit + push systématique ») |

