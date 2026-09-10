# runtime·session-tooling — quel outil pm-* pour quelle opération ; demandes, notifications, RM-id
Ouvrir quand : je cherche l'outil PM d'une opération touchant l'état d'une tâche/branche/repo/Redmine · une demande arrive · un événement notable · je viens de créer un ticket. Source : `norms/src/modules/session-tooling.md`.

Skills `mmi-pm-<verbe>` ≡ `mmi-pm <verbe>` (ex. `mmi-pm-task-add` = `pm-task-add.py`). Cheatsheet `norms/CHEATSHEET.md` (généré par `pm-norms-assemble.py cheatsheet`, ≤ 1 200 tokens : 1 ligne par outil + flux nominaux take → deliver, porcelain) : le lire UNE fois en début de session au lieu des `--help` répétés (300–600 tokens chacun ; `--help` court, `--help-full` complet).
Garde de périmètre : les outils MUTANTS (`pm-task-link`, `-status-update`, `-comment`, `-protocol`, `-description-update`) REFUSENT un ticket d'un autre projet que le workspace courant si l'id n'a jamais été vu dans la session (empreinte d'un id prédit) ; voulu ⇒ `--cross-project`.

## Outillage obligatoire (garde-fou 1)
En session PM (workspace `.mmi-pm` ou repo PM), état des tâches / branches / repos-submodules / tickets Redmine ⇒ scripts/skills PM, jamais à la main : garantit Redmine ↔ MD ↔ worklog et les couplages (auto-assignation, notes, `status_history`, logs, filigrane IA, temps/tokens). Pas d'outil = trou à combler. Tout ce qui amende l'état d'une tâche passe par `pm-task-status-update.py` (source unique des transitions : Redmine + MD + log + worklog). Le worklog de session (`pm-session-status.py`) est alimenté automatiquement via `pm_session_hook.py` ; stores keyés par `session_id` (spawn, jonction ticket ↔ session) : `knowledge/karl-agent/sessions.md`.

## Couverture (domaine · opération → outil)
- Tâche · créer → `pm-task-add.py` (`--porcelain` = id nu) · statut → `pm-task-status-update.py` · commenter → `pm-task-comment.py` · lier (relates/depends/blocks) → `pm-task-link.py` · déplacer vers un autre projet PM (fiche + `.log` + `.reporting`, `project_id` Redmine vérifié) → `pm-task-move.py <id> --to <client>/<projet>` · description/checklist → `pm-task-description-update.py` · estimation (CF prévisionnels) → `pm-task-metrics-push.py --estimate` · temps/tokens (hook) → `pm-task-tick.py` · report conso → Redmine (time_entries + CF17) → `pm-task-report.py` · sync depuis Redmine → `pm-task-sync.py` · lister/afficher → `pm-task-list.py`, `pm-task-show.py` · reprendre sans sa session (séances, prochaine étape, demandes, état du code) → `pm-task-brief.py <id> --reprise` · branche de ticket (+ CF GIT Branche) → `pm-branch-start.py` (`--worktree --print-cd` = chemin nu) · se placer dans le worktree → `cd "$(pm-task-cd.py <id>)"`
- Donnée PM · commit+push des écritures de scripts → automatique (`pm_git.autocommit`, silencieux si OK, `--no-commit` débraye) · rattrapage des édits libres non commités > 1 h → automatique, commit `pm(rattrapage): …` séparé à chaque autocommit (`git.sweep: false`, `git.sweep_after_min`)
- Repo · protection de branches (code ou core) → `pm-protect.py` (`--repo`, `--all-cores`) · promouvoir intégration → prod → `pm-promote.py` (transition, hors flux nominal)
- Instance · pont d'onboarding des workspaces (`AGENTS.md` + `CLAUDE.md`) → `pm-workspace-bridge.py` (nu = contrôle, `--install`, `--update`)
- Projet · cohérence cross-projet (used_by/provided, implements) → `pm-doctor.py` · créer/bootstrap → `pm-project-new.py`, `pm-project-bootstrap.py`, `pm-client-new.py`
- Contact · annuaire (ajout, fusion, recherche par adresse, migration) → `pm-contact.py` · rattacher à un client (rôle, titre) → `pm-client-contact.py`
- Redmine bas niveau · note / fetch / tag IA / config → `redmine-post-note.py`, `redmine-fetch-*.py`, `redmine-tag-ia.py`, `redmine-config-check.py`
- Session · worklog → `pm-session-status.py` · archiver transcripts (+ `history.jsonl`, worklogs) et surveiller → `pm-sessions-archive.py` (`--check`, `--install-timer`) · événement notable → `pm-session-status.py notify` · demande du demandeur → `pm-session-status.py request` · consigner les décisions dans le journal du ticket → `pm-decisions.py persist <id>`
- Branches/repos/submodules · commit+push conventionné, base de version → TROU, aucun outil dédié (cf. git-mep).

## Notifications importantes
Un incident en séance se perd au défilement : le consigner SUR-LE-CHAMP : `pm-session-status.py notify "<fait>" --kind <type> [--ref RM<id>]` ; types `secret` (→ `critical` ; la rotation reste à faire), `refus`, `garde-fou`, `outillage`, `decision`. Fait notable et actionnable, jamais un commentaire. La refermer une fois traitée : `notify --resolve <n> --ticket RM<id>` (sort du backlog sans supprimer, archivée avec le ticket) ; `--clear` DÉTRUIT, pas le geste courant. Skill `mmi-pm-session-status`.

## Registre des demandes
Enregistrer CHAQUE demande dès réception, avant de savoir si elle sera ticketée : `pm-session-status.py request "<la demande>"` ; puis `request --set <n> --status ticketee --ticket RM<id>` (ou `repondu` / `annulee` / `fusionnee --merged-into <n>`). Ne pas filtrer (« fais une sous-tâche » est une demande) ; en doute, enregistrer. Contrôle : `request --audit` (registre vs transcript). N'enregistre PAS ce qui ne vient pas du demandeur (résumé de compaction, collage de console, sortie de commande) ; si glissé, ranger en `non_demande`, pas `annulee`.

## Idiomes
- Contenu long/multi-ligne par stdin ou fichier : `pm-task-comment <id> --note - < note.md`, `redmine-post-note <id> --note -`, `pm-task-add --description -` / `--description-file <path>`, `pm-task-description-update <id> --set-from-file <path>` (évite aussi la protection Bash « newline + `#` » de Claude Code).
- Transitions valides : `pm-task-status-update <id> --list-next`.
- Assignation : `en_cours` auto-assigne (`--assign-to me` implicite) ; `--assign-to <id|me|author>` force, `--no-assign` débraye.
- Projet ambigu : `--project entity/project` (`pm-task-add`, `pm-task-list`…).
- `--dry-run` sur `pm-task-add`, `pm-task-status-update`, `pm-task-sync`.
- Worktree sans `.env` : préfixer `PM_CORE_DIR=<racine du repo PM actif>`.

## Capturer un RM-id (garde-fou 13)
Séquence Redmine globale à l'instance, en concurrence ⇒ jamais « dernier id + 1 ». `pm-task-add.py --porcelain` (alias `--id-only`) imprime l'id nu sur stdout (logs sur stderr) :
```bash
ID=$(pm-task-add --title "…" --type feature --porcelain)
pm-task-status-update "$ID" en_cours
pm-branch-start "$ID" --take
pm-task-link add "$ID" 1834 --type relates
```
Toute commande enchaînée consomme `$ID`, jamais un littéral. Sans `--porcelain` : `ID=$(pm-task-add … | grep -oE 'RM[0-9]+' | head -1)` (moins robuste).
