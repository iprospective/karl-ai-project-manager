<!--
  SOURCE CANONIQUE VERSIONNÉE du fichier de pont /zfs/workspaces/AGENTS.md.

  Le fichier déployé (/zfs/workspaces/AGENTS.md, + symlink CLAUDE.md → AGENTS.md) est
  HORS GIT (artefact de provisioning par instance, cf. RM1892). Ce template est sa
  référence versionnée : à chaque provisioning d'instance (ou après une évolution de
  l'onboarding worker, ex. le switchover KERNEL de RM1922), (re)copier ce fichier vers
  /zfs/workspaces/AGENTS.md et créer le symlink CLAUDE.md → AGENTS.md.

  Garder ce template et le fichier déployé SYNCHRONES — c'est ce qui empêche les
  instances de la fédération de dériver sur un onboarding périmé.
-->
# AGENTS.md — racine des workspaces

Instructions pour **tout agent / LLM** (Claude, opencode, …) travaillant sous
`/zfs/workspaces/`. Lu automatiquement par remontée d'arborescence depuis n'importe
quel sous-workspace.

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
