---
type: procedure
product: karl-agent
created: 2026-07-28
refs: [RM2418, RM2391, RM2144, RM1939]
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
