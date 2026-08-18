> 📂 **Module `session-tooling` — quand lire ceci :** je cherche quel outil PM utiliser pour une opération touchant l'état d'une tâche/branche/repo/Redmine.
> **Outils :** tous les `pm-*` · **Préchargé par :** tous.

## Cheatsheet outillage (RM2367, CDC RM2316 § S6)

**`norms/CHEATSHEET.md`** (généré : `pm-norms-assemble.py cheatsheet`, ≤ 1 200
tokens) : 1 ligne par outil du quotidien + les flux nominaux (take → deliver,
porcelain, lectures ciblées). **Le lire UNE fois en début de session** remplace
les `--help` répétés (300–600 tokens chacun) ; `--help` reste court par défaut,
`--help-full` donne le pavé complet.

> **Garde de périmètre (RM2274).** Les outils MUTANTS (`pm-task-link`, `-status-update`,
> `-comment`, `-protocol`, `-description-update`) REFUSENT d'écrire sur un ticket d'un
> autre projet que le workspace courant si l'id n'a jamais été vu dans la session —
> l'empreinte d'un id prédit (tripwire #13). Écriture cross-projet voulue : `--cross-project`.

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
| Tâche | créer | `pm-task-add.py` · `mmi-pm-task-add` (`--porcelain` = id nu sur stdout) |
| Tâche | changer le statut | `pm-task-status-update.py` · `mmi-pm-task-status-update` |
| Tâche | commenter | `pm-task-comment.py` · `mmi-pm-task-comment` |
| Tâche | lier (relates/depends/blocks) | `pm-task-link.py` · `mmi-pm-task-link` |
| Tâche | description / checklist | `pm-task-description-update.py` |
| Tâche | estimation (CF prévisionnels) | `pm-task-metrics-push.py --estimate` |
| Tâche | mesure temps/tokens (hook) | `pm-task-tick.py` |
| Tâche | report conso → Redmine (time_entries + CF17) | `pm-task-report.py` |
| Donnée PM | commit+push des écritures de scripts | *(automatique — `pm_git.autocommit`, RM1834 ; **silencieux si ça passe**, RM2440 ; `--no-commit` pour débrayer)* |
| Repo | protection de branches (code **ou** core) | `pm-protect.py` (`--repo` · `--all-cores`) |
| Repo | promouvoir intégration → prod | `pm-promote.py` — ⚠ **transition** (RM2440), hors flux nominal |
| Tâche | démarrer la branche de ticket (+ CF GIT Branche) | `pm-branch-start.py` (`--worktree --print-cd` = chemin nu à `cd`) |
| Tâche | se (re)placer dans le worktree du ticket | `pm-task-cd.py` — `cd "$(pm-task-cd.py <id>)"` (RM2240) |
| Projet | cohérence des paires cross-projet (used_by/provided, implements) | `pm-doctor.py` |
| Tâche | sync depuis Redmine | `pm-task-sync.py` · `mmi-pm-task-sync` |
| Tâche | lister / afficher | `pm-task-list.py`, `pm-task-show.py` |
| Projet / client | créer / bootstrap | `pm-project-new.py`, `pm-project-bootstrap.py`, `pm-client-new.py` |
| Ticket Redmine (bas niveau) | note / fetch / tag IA / config | `redmine-post-note.py`, `redmine-fetch-*.py`, `redmine-tag-ia.py`, `redmine-config-check.py` |
| Session | worklog d'avancement | `pm-session-status.py` · `mmi-pm-session-status` |
| Session | **événement notable** (secret exposé, refus, garde-fou, outillage en défaut, décision bloquante) | `pm-session-status.py notify` |
| Session | **demande du demandeur** (avant même de savoir si elle sera ticketée) | `pm-session-status.py request` |
| Session → tâche | **consigner les décisions** (questions tranchées / restées sans réponse) dans le journal du ticket | `pm-decisions.py persist <id>` |
| **Branches / repos / submodules** | créer branche par ticket, commit+push conventionné, base de version | **⚠ trou — aucun outil dédié** (cf. § « Branche de travail par ticket », § « Commit + push systématique ») |

## Notifications importantes de session (RM2466)

Un incident rencontré en séance se perd au défilement : **consigne-le sur-le-champ**
(pas « à la fin »), `pm-session-status.py notify "<fait>" --kind <type> [--ref RM<id>]`.
Types : `secret` (→ `critical` ; la **rotation** reste à faire), `refus`, `garde-fou`,
`outillage`, `decision`. Un fait notable et actionnable, jamais un commentaire — un
canal noyé ne sera pas lu.

**Et referme-la quand elle est traitée** (RM2715) : `notify --resolve <n> --ticket
RM<id>`. Une notification dit ce qu'il reste à faire ; laissée telle quelle après
coup, elle porte une consigne périmée (« ticket à ouvrir » alors qu'il l'est) et
use la crédibilité du canal. Résoudre la sort du backlog **sans** la supprimer —
elle reste en archive avec le ticket qui l'a portée. `--clear`, lui, DÉTRUIT :
ce n'est pas le geste courant. Mode d'emploi : skill `mmi-pm-session-status`.

## Registre des demandes (RM2621)

Une demande formulée en séance n'existe que dans le fil : non ticketée
sur-le-champ, elle disparaît au premier défilement.

**Règle — enregistre CHAQUE demande dès réception**, avant de savoir si elle
sera ticketée : `pm-session-status.py request "<la demande>"`. Puis, quand son
sort est connu : `request --set <n> --status ticketee --ticket RM<id>` (ou
`repondu` / `annulee` / `fusionnee --merged-into <n>`). Enregistrer coûte une
ligne ; oublier ne laisse aucune trace.

Ne filtre pas à la réception : « fais une sous-tâche » fait 19 caractères et
c'est une demande. En cas de doute, enregistre — une entrée en trop se classe,
une demande perdue ne se retrouve pas. Contrôle : `request --audit` compare le
registre au transcript. Mode d'emploi : skill `mmi-pm-session-status`.

**N'enregistre pas ce qui ne vient pas du demandeur** (RM2635) : résumé de
compaction réinjecté dans le fil, collage de console renvoyé à TA demande,
sortie de commande. Ce ne sont pas des demandes et ils noient les vraies. Si
l'une s'est glissée dans le registre, elle se range en `non_demande` — pas en
`annulee` : personne n'a rien annulé, et ranger le bruit sous un statut faux
rend le registre inexploitable pour la question à laquelle il sert à répondre.

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

### Capture d'un RM-id fraîchement créé — jamais de prédiction (tripwire #13)

La séquence des ids Redmine est **globale à l'instance** : plusieurs agents et
plusieurs projets créent des tickets **en concurrence**. Le prochain id n'est donc
**jamais prévisible** — « dernier id vu + 1 » est une **erreur structurelle** (deux
incidents en deux jours : RM2142 puis RM2163, prises/branches/statuts posés sur le
mauvais ticket, à corriger après coup).

**Règle** : après une création, **capturer** l'id depuis la sortie de l'outil, ne
jamais le retaper de mémoire. `pm-task-add.py` expose **`--porcelain`** (alias
`--id-only`) qui n'imprime que **l'id nu sur stdout** (tous les logs partent sur
stderr) — la capture devient triviale et fiable :

```bash
ID=$(pm-task-add --title "…" --type feature --porcelain)   # ex. → 2170
pm-task-status-update "$ID" en_cours
pm-branch-start "$ID" --take
pm-task-link add "$ID" 1834 --type relates
```

Toute commande enchaînée **consomme la variable `$ID`**, jamais un littéral. Sans
`--porcelain`, capturer sur le format verbeux : `ID=$(pm-task-add … | grep -oE 'RM[0-9]+' | head -1)` (moins robuste — préférer `--porcelain`).

