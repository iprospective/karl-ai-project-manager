---
type: procedure
product: karl-agent
created: 2026-07-28
refs: [RM2418, RM2391, RM2144, RM1939, RM2068, RM2991, RM2997]
---

# karl-agent — sessions Claude Code : stockage, host↔conteneur, déplacement

Où vivent les sessions reprenables du cockpit, ce qui est partagé entre l'hôte et
le conteneur `dev`, et comment déplacer proprement une session d'un projet à un autre.

## Le cockpit tourne DANS le conteneur `dev`

`karl-agent.py` (serveur HTTP) et les tmux `karl-*` s'exécutent dans le conteneur LXC
`dev` (`hostname` = `dev.local`). Toute opération sur les fichiers de session doit
donc viser le système de fichiers **du conteneur**.

## Deux stockages, deux régimes de partage

| Chemin | Rôle | Partagé hôte↔conteneur ? |
|---|---|---|
| `~/.claude/projects/<slug>/<sid>.jsonl` | **transcript** de la conversation (source de `--resume`) | **OUI** (même inode) |
| `~/.local/state/karl-agent/sessions/<engine>/<sid>.json` | **store per-session** karl (dont le `cwd` de relance) | **NON** (stores distincts) |
| `~/.claude/session-worklogs/<sid>.json` (+ `.md`) | **worklog PM** de la session (RM2068) | **OUI** |
| `~/.local/state/karl-agent/tasks/<client>/<projet>/RM<id>-<n>.json` | **jonction ticket ↔ session** | **NON** |

## Archivage — ce qui protège vraiment (RM2997)

`~/.claude/projects` est un dépôt git (remote `claude-projects-sessions`).
**Un commit local suffit à immuniser un transcript** : git garde le blob même
quand Claude Code efface le fichier. Le push met hors machine ; la protection,
elle, commence au commit.

`pm-sessions-archive.py` fait les deux, toutes les heures (timer systemd
`--user`), et archive aussi `history.jsonl` et les worklogs — sous `_meta/`, à
une profondeur qui ne les fasse pas passer pour des transcripts (le moteur
énumère `*/*.jsonl`, profondeur **deux** exactement).

Deux invariants, appris à la dure :

- **aucune suppression n'est consignée.** Un transcript déjà effacé doit garder
  son blob atteignable dans l'historique — c'est ce qui a permis d'en récupérer
  313. Consigner sa disparition le retirerait de l'arbre courant, et un clone
  frais ne le ramènerait plus.
- **un verrou ne se lève que mort** : plus vieux que 15 min ET aucun git vivant
  dans le dépôt. Le 2026-06-23, un `.git/index.lock` laissé par un git
  interrompu a fait échouer chaque archivage pendant **75 jours sans un mot** —
  aucun cron, aucun log, aucune alerte, le geste étant manuel. Le verrou est mis
  de côté (`index.lock.perime-<epoch>`), jamais détruit.

Surveillance : `pm-sessions-archive.py --check` (âge du dernier commit, commits
non poussés, verrou) est branché sur le contrôle d'environnement de karl-agent
(`_envchk_sessions_archive`, niveau `error`) — ce qui est perdu ici ne se
rattrape pas.

## Le worklog : les métadonnées PM d'une session (RM2068, RM2991)

`~/.claude/session-worklogs/<sid>.json` est **le** fichier de métadonnées d'une
session — keyé par le même `session_id` que le transcript, alimenté
automatiquement par les scripts PM (via `pm_session_hook.py`) :

| Clé | Contenu |
|---|---|
| `items[]` | un par ticket touché : `ref` (`RM2703`), `label` (**le titre du ticket**), `project`, `status`, `opened_status`, `note`, `next`, `commit`, `ts` |
| `requests[]` | **le texte des demandes** telles que formulées, + `status` (ticketée ou non) et `ticket` |
| `notifications[]` | événements notables consignés en séance (`level`, `kind`, `ref`, `message`) |

Le `.md` du même nom en est le rendu lisible (celui que sert `mmi-pm
session-status`). Le tout pèse ~0,5 Mo pour une centaine de sessions, contre
~400 Mo de transcripts : **c'est ici qu'on cherche**, pas dans les `.jsonl`.
`op_resumable` (recherche du panneau de reprise, RM2991) s'appuie exactement sur
ces trois listes, plus les jonctions et l'index des titres de tickets ; le
transcript n'est balayé que sur demande explicite (`deep=1`).

⇒ Éditer le store per-session **depuis l'hôte** touche le mauvais fichier : le store que
lit `op_resume` est celui **du conteneur**. Symptôme classique (RM2391) : on « corrige »
la session depuis l'hôte, la reprise repart quand même au mauvais projet.

Depuis l'hôte, on peut voir/écrire le FS du conteneur via `/proc/<pid>/root/…` (pid d'un
process du conteneur), mais le bon réflexe est de **travailler dans le conteneur**.

- `<slug>` = le `cwd` avec chaque `/` et `.` remplacés par `-`
  (`/zfs/workspaces/calicote/prestashop` → `-zfs-workspaces-calicote-prestashop`).
  La transformation est **lossy** (on ne peut pas remonter au `cwd` depuis le slug seul).

## Les 3 ancrages d'une session à un projet (leçon RM2391)

Une session est liée à un projet par **trois** endroits ; n'en corriger qu'un ou deux
laisse la session repartir au mauvais projet ou disparaître de la liste de reprise :

1. **Le transcript** `~/.claude/projects/<slug>/<sid>.jsonl` — son emplacement (`<slug>`)
   est ce que `claude --resume` cherche depuis le `cwd` de relance.
2. **Les `cwd` internes** du transcript — pilotent le **regroupement d'affichage**
   (`op_resumable` lit la queue du `.jsonl` via `_jsonl_tail_meta`, puis
   `_pm_project_of_cwd`).
3. **Le store per-session** `…/karl-agent/sessions/<engine>/<sid>.json`, champ `cwd`
   — **le critique** : `op_resume` le lit pour relancer `claude --resume` au bon `cwd`.
   Périmé → relance au mauvais dossier → « No conversation found ».

## Déplacer une session proprement

**Toujours session à l'ARRÊT** : un `claude --resume`/tmux vivant ré-estampille la queue
et peut recréer le transcript.

- **Cockpit** : panneau « Reprendre une session » → bouton **⇄** sur la ligne (visible au
  survol) → choisir le projet cible. Appelle `POST /move-session`.
- **CLI** (conteneur) : `karl-move-session --session <sid> --to /zfs/workspaces/<c>/<p>
  [--dry-run]` — corrige les 3 ancrages, refuse si la session est vivante, avertit si
  lancé hors conteneur (`hostname` ≠ `dev.local`).

`POST /move-session {session_id, (client, project | to_cwd), [force]}` :
- résout la destination : `to_cwd` explicite, ou `(client, projet)` → workspace via le
  `.mmi-pm` (`_resolve_workspace`, plus sûr qu'un chemin fourni par le client) ;
- refuse `409` si la session est vivante (tmux ancré OU `claude --resume` en process) ;
- déplace le transcript, réécrit ses `cwd` internes, réécrit le store per-session (+ les
  jonctions ticket) ; renvoie `{old_slug, new_slug, cwd, client, project}`.

## Robustesse `op_resume` (RM2418)

`op_resume` ne fait plus aveuglément confiance au store per-session : `_resume_cwd`
retient le premier candidat — store per-session, puis `cwd` interne du transcript — dont
le **slug == dossier où vit réellement le `.jsonl`**. Un déplacement manuel du transcript
(sans MAJ du store) ne casse donc plus la reprise.
