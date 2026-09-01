<!--
  SOURCE CANONIQUE VERSIONNÉE du fichier de pont /zfs/workspaces/AGENTS.md.

  Le fichier déployé (/zfs/workspaces/AGENTS.md, + symlink CLAUDE.md → AGENTS.md) est
  HORS GIT (artefact de provisioning par instance, cf. RM1892). Ce template est sa
  référence versionnée : à chaque provisioning d'instance (ou après une évolution de
  l'onboarding worker, ex. le switchover KERNEL de RM1922), (re)copier ce fichier vers
  /zfs/workspaces/AGENTS.md et créer le symlink CLAUDE.md → AGENTS.md.

  Garder ce template et le fichier déployé SYNCHRONES — c'est ce qui empêche les
  instances de la fédération de dériver sur un onboarding périmé.

  Déploiement OUTILLÉ (RM1892) — ne plus recopier à la main :
      scripts/pm-workspace-bridge.py            # que dit l'instance ? (contrôle)
      scripts/pm-workspace-bridge.py --install  # première pose (fichier + symlink)
      scripts/pm-workspace-bridge.py --update   # rafraîchit le générique, GARDE l'instance

  Le bloc délimité BEGIN/END INSTANCE ci-dessous est la part machine : le template
  n'en fournit qu'un défaut, et `--update` ne l'écrase jamais.
-->
# AGENTS.md — racine des workspaces

Instructions pour **tout agent / LLM** (Claude, opencode, …) travaillant sous
`/zfs/workspaces/`. Lu automatiquement par remontée d'arborescence depuis n'importe
quel sous-workspace.

<!-- BEGIN INSTANCE — propre à CETTE machine. Tout ce qui est entre ces
     deux marqueurs est PRÉSERVÉ par `pm-workspace-bridge.py --update` :
     c'est là, et seulement là, que vont les chemins, hôtes et usages
     d'une instance donnée. Le reste du fichier vient du template versionné. -->
## Contexte d'exécution — sache d'où tu démarres

**Vérifie-le, ne le suppose pas** : `hostname` te dit où tu tournes.

_(Section à renseigner au provisioning de l'instance : où s'exécute la session
(hôte ou conteneur), ce qui est local et ce qui passe par SSH, l'état des clés et
des agents, le transport git des remotes, et les branches protégées. Voir le
`AGENTS.md` d'une instance déjà provisionnée pour le niveau de détail attendu.)_

### Deux copies du repo PM : PROD vs DEV — ne pas les confondre

Sur MathouDell le repo PM (GitLab `iprospective/ai-artificial-intelligence/ai-pm-core`,
project id **138**) existe en **deux copies de travail, intentionnellement** — ce
n'est PAS un double-checkout cassé :

- **`/zfs/workspaces/.mmi-pm-core` = la PROD PM.** C'est elle qui fait tourner le
  système PM en live (scripts `pm-*.py`, hooks, NORMS de référence). **Root-owned
  volontairement** : depuis l'hôte en tant que `mathieu` tu **ne peux pas** y écrire
  ni y `git fetch` (permission refusée sur `.git`) — c'est normal, **ne force pas
  avec sudo** sans feu vert. L'alias `…/ai/project-management` (le lien `.mmi-pm` de
  plein de projets) pointe ici.
- **`/zfs/workspaces/iprospective/ai-project-management` = l'ENV de DEV PM**
  (`mathieu:mathieu`). C'est là qu'on **développe l'outillage PM** et là que
  `pm-task-add` & co écrivent quand le projet est résolu via `--project`. Des
  changements non-committés y sont du **WIP normal**, pas une anomalie.

**Pousser le repo PM** : le remote de la copie dev est **HTTPS + token**, or les
credential-helpers à token (`git-credential-pm-*`) n'existent **que dans le
conteneur `dev`**. Depuis l'hôte, un push du repo PM **échoue en auth** → **pousse
depuis le conteneur** (`ssh mathieu@dev.lxc`). `main` protégée (RM2030) →
`git push origin main:dev` puis **MR dev→main** (token *manager*, API projet
id **138**, résolution par match **exact** du `path_with_namespace`). Symptôme
typique quand on l'ignore : « auto-push différé » qui s'accumule.

<!-- END INSTANCE -->

## D'abord : es-tu dans un workspace PM-tracké ?

Regarde la racine de ton **workspace courant** : s'il contient un symlink
**`.mmi-pm`**, ce projet est piloté par le système de gestion de projet (PM)
iProspective et **tu es un agent worker PM** → applique tout ce qui suit.

Sinon (pas de `.mmi-pm` à la racine de ton workspace — repos non reliés au PM,
scratch / expérimentations, sessions d'audit…), **ces règles ne s'appliquent pas** :
suis les instructions propres au dossier.

> **Cas du repo PM lui-même** (`…/ai/project-management`) : il **a** un `.mmi-pm`
> (c'est le projet `pm-ai-agents` — le système se gère lui-même via PM) et possède
> son propre `CLAUDE.md`. La condition s'y applique donc légitimement et pointe vers
> les mêmes NORMS / worker-docs que son `CLAUDE.md` référence déjà : redondant, pas
> contradictoire. Rappel : le protocole worker ne se déclenche que sur une
> invocation explicite « traite la tâche RM<id> » — une session méta/interactive
> n'est pas concernée.

## Si oui — onboarding obligatoire AVANT toute action

1. **Résous `.mmi-pm`** : il pointe vers le dossier PM du projet
   (`…/project-management/projects/clients/<client>/projects/<projet>/`) et te donne
   donc le **client** et le **projet**.
2. **Remonte à la racine du repo PM** (le dossier contenant `norms/` et
   `agents/`) et lis, dans l'ordre :
   - `CLAUDE.md` / `AGENTS.md` — instructions générales du système PM ;
   - `norms/src/NORMS-KERNEL.md` — le **KERNEL** (lecture obligatoire) : table des
     **déclencheurs** + **tripwires**. Tu ouvres un module `norms/src/modules/*.md`
     **uniquement quand son déclencheur se présente** — pas tout d'un coup.
     (`norms/NORMS.md` = doc complet *généré*, pour référence ; ne pas l'éditer.) ;
   - `agents/worker-common.md`, puis `agents/worker-<ton rôle>.md`.
3. Les tâches sont dans `<.mmi-pm>/tasks/RM<id>_*.md` (+ leur `.log.md`).

## Protocole quand on te confie une tâche

« traite / continue / review / chiffre la tâche **RM<id>** » ⇒ protocole worker NORMS :

- **Cascade** client → projet → tâche (héritage avec override).
- **Optimistic locking** : vérifie le champ `updated` de la tâche avant d'écrire.
- **Flow d'états** : transitionne le statut quand tu prends / avances / livres la
  tâche (la prise en charge `en_cours` implique l'auto-assignation — voir le KERNEL).
- **Sync Redmine** à chaque changement de statut ; **append au `.log.md`** à chaque
  étape significative.
- Tu n'écris **que** dans les fichiers dont tu es propriétaire (cf. `worker-common.md`).

## Portabilité (fédération)

`.mmi-pm` est un lien **absolu** propre à CETTE machine. Sur une autre instance
(clone git indépendant), le chemin diffère — **résous le lien, ne code jamais le
chemin en dur.** Le fichier déployé `/zfs/workspaces/AGENTS.md` est un **artefact de
provisioning de la machine** (hors git) : sur une nouvelle instance, il doit être
provisionné depuis ce template (cf. install karl-agent / instance).
