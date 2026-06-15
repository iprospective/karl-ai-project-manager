# Bascule du résolveur — blueprint (C3 / RM1949)

| | |
|---|---|
| **Statut** | BLUEPRINT — à exécuter en **session dédiée** (geste le plus à risque du chantier) |
| **Date** | 2026-06-15 |
| **Objet** | Rendre les `.mmi-pm` co-localisés **canoniques** ; `ai-projects` devient archive/vue |

## Pourquoi c'est le geste à part

Toute la co-location a été **additive et réversible** : `ai-projects` est resté la donnée
**canonique**, les `.mmi-pm` sont des **copies**. La bascule change ça — c'est le seul
geste qui modifie **où tous les outils PM lisent/écrivent**. Une erreur casse find_task,
les transitions, l'écriture des tâches… donc : **session dédiée, contexte frais, pilote
d'abord, tests exhaustifs.**

## Mécanisme retenu — symlink-vue + patch résolveur (incrémental)

Le résolveur (`pm_paths.py`) lit tout depuis `projects_root` (ai-projects) via les patterns
de `pm.config.yml`, et **`iter_projects` ignore les symlinks**. Idée :

1. **Patch `iter_projects`** : suivre les symlinks (`if p.is_dir()` au lieu de
   `... and not p.is_symlink()`), + **dédup par cible résolue** (anti double-comptage).
   → Avec ce patch, un projet en **dossier réel** (non basculé) résout vers ai-projects,
   un projet **symlinké** (basculé) résout vers son `.mmi-pm`. **Les deux marchent
   simultanément** → bascule **client par client** possible. (Le niveau client —
   `client/`, `memory/`, `projects_used/` — se résout par chemin direct qui suit déjà les
   symlinks ; pas de patch.)
   *NB cross-client* : aujourd'hui 0 symlink actif dans `projects/` → pas de régression ;
   la dédup couvre le futur.

2. **Re-sync préalable (par projet)** : les `.mmi-pm` ont **divergé** depuis la
   co-location (les écritures de la session sont allées dans ai-projects). Avant de
   basculer un projet, **recopier ai-projects/…/P → `.mmi-pm`** pour le rendre courant.
   ⚠ Gérer aussi le contenu non copié à la co-location : le symlink `workspace`
   (recréable), `.wiki-sync` (régénérable) — décider inclus/exclus.

3. **Flip (par projet)** :
   - `ai-projects/clients/<C>/projects/<P>` (dossier réel) → **archiver** (backup) →
     **remplacer par un symlink** → `<workspace>/.mmi-pm`.
   - niveau client (1×/client) : `clients/<C>/{client,memory,projects_used}` →
     symlinks → `<client-workspace>/.mmi-pm-client/{…}`.

4. **Tests (obligatoires avant de généraliser)** : `find_task`, `iter_projects`,
   `pm-task-list`, `pm-doctor`, **round-trip complet** (`pm-task-status-update` /
   `pm-task-comment` sur un ticket pilote → vérifier que l'écriture atterrit dans le
   `.mmi-pm` co-localisé, pas dans ai-projects).

## Plan d'exécution (session dédiée)

- **P0** — snapshot ZFS + branche.
- **P1** — patch `iter_projects` (suivre symlinks + dédup) + **tests de non-régression**
  (tout en dossiers réels → résultats identiques à aujourd'hui).
- **P2** — **pilote calicote** : re-sync + flip des 4 projets + client ; round-trip ;
  doctor. Les autres clients restent en dossiers réels (ai-projects). Valider.
- **P3** — généraliser client par client (au fil de l'eau, chacun réversible).
- **P4** — quand tout est basculé : `ai-projects` → archive en lecture seule ;
  `pm-workspace-sync` (RM1948) pour reconstruire la vue/cloner un périmètre.
- **P5** — déménagement de l'outil (P6 / RM1945) + clone fédéré, **après** la bascule.

## Réversibilité

Chaque flip est réversible : retirer le symlink, restaurer le dossier réel depuis le
backup, `git revert` du patch. Le snapshot ZFS (P0) est le filet ultime.

## Outillage à écrire

- `pm-resolver-flip.py <client>` : re-sync + archive + symlink (par client, idempotent,
  `--dry-run`, anti-fuite).
- Patch `pm_paths.iter_projects` + test dédié.
- (option) `pm-doctor` : check « tout `.mmi-pm` ↔ symlink ai-projects cohérent ».
