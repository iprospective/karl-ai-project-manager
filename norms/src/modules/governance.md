> 📂 **Module `governance` — quand lire ceci :** gouvernance HORS-runtime : déploiement multi-machines · versionning de NORMS · distribution des skills · config globale.
> **Outils :** `pm-norms-assemble`, `pm-norms-doctor`, `pm-context-budget` · **Préchargé par :** —.

## Architecture de déploiement

### V1 — Machine unique (recommandée pour démarrer)

Tous les agents tournent sur la même machine. L'inférence LLM est déjà distante (API Anthropic). Aucune configuration réseau requise.

```
┌─────────────────────────────────────────────────┐
│  Serveur principal                              │
│                                                 │
│  ┌─────────────┐  ┌──────────┐  ┌──────────┐   │
│  │Orchestrateur│  │ Worker A │  │ Worker B │   │
│  │  (n8n)      │  │          │  │          │   │
│  └──────┬──────┘  └────┬─────┘  └────┬─────┘   │
│         └──────────────┴─────────────┘          │
│                        ▼                        │
│          /zfs/workspaces/ai/project-management  │
└─────────────────────────────────────────────────┘
          │                        │
          ▼                        ▼
   Anthropic API             Redmine (local)
   (inférence LLM)
```

### V1.5 — NFS sur ZFS (ajout de serveurs sans refonte)

ZFS supporte nativement le partage NFS. Le dossier de travail est monté sur les serveurs additionnels. Les agents sur tous les serveurs voient le même filesystem. Le protocole optimistic locking (`updated`) est indispensable à ce stade.

```
Serveur principal (ZFS)                 Serveur B
┌─────────────────────────┐             ┌──────────────────┐
│ /zfs/workspaces/ai      │───NFS──────►│ /mnt/ai-workspace│
│                         │             │ Worker B, C      │
│ Orchestrateur           │◄────────────│                  │
│ Worker A                │             └──────────────────┘
└─────────────────────────┘
```

Activation du partage NFS sur ZFS :
```bash
zfs set sharenfs="rw=@192.168.x.0/24,sync,no_subtree_check" zfs/workspaces/ai
```

Limites : latence sur les écritures, garanties d'atomicité réduites entre serveurs distants.

### V2 — Git/branches GitLab (distribution robuste)

Chaque serveur a un clone local du repo GitLab ; les agents travaillent sur des branches dédiées et Git gère la synchronisation et la détection de conflits au merge. C'est la solution la plus robuste pour distribuer le travail sans NFS.

Cette architecture ne définit **que** la distribution des agents sur plusieurs machines. Le **workflow de branches et de release** (nommage des branches de ticket, branche d'intégration, preprod, MEP) est décrit une seule fois en § *Cycle de développement → test → mise en production* — ne pas le redéfinir ici.

**Avantages :** distribution réelle sans NFS, historique complet des changements, détection de conflits native.

### Choix selon le contexte

| Situation | Architecture |
|---|---|
| Démarrage, 1 serveur | **V1** |
| Ajout rapide de 1-2 serveurs | **V1.5** (NFS) |
| Scalabilité et robustesse | **V2** (Git/branches) |
| Très grand volume, état centralisé | V3 — base de données (future) |

---

## Configuration globale

Les valeurs sensibles (tokens, URLs d'instance) sont définies dans `.env` (gitignored).
Copier `.env.example` en `.env` et renseigner les variables avant utilisation.

```yaml
gitlab:
  instance: ${GITLAB_URL}
  ssh: ${GITLAB_SSH}
  token: ${GITLAB_TOKEN}

redmine:
  instance: ${REDMINE_URL}     # global, peut être surchargé dans project.md
  api_key: ${REDMINE_API_KEY}
```

La résolution des chemins est centralisée dans `pm.config.yml` (cf. section
suivante). Plus aucun chemin filesystem n'est dérivé en concaténation manuelle
dans le code ou la doc.

## Skills PM (distribution cross-instance)

Le dossier `skills/` du repo PM héberge les **skills Claude Code** (`SKILL.md`) qui font
partie de l'outillage PM et doivent être disponibles sur **toutes les instances**. C'est
le canal de distribution cross-instance des skills — distinct des skills personnels
(`~/.claude/skills`, repo `claude-skills`) et des skills agents (`~/.agents/skills`).

Claude Code n'auto-découvre les skills que depuis `~/.claude/skills/` (ou le `.claude/skills/`
d'un projet, ou les plugins). Un `SKILL.md` versionné dans `skills/` n'est donc invocable
qu'une fois **symlinké** dans le dossier skills de l'utilisateur, via
`scripts/pm-skills-sync.py` (à lancer au setup de l'instance puis après tout pull qui
ajoute/retire un skill). Le script est idempotent, ne supprime jamais un vrai dossier
(collision de nom → averti, ignoré) et n'agit que sur ses propres symlinks. Détails et
convention : `skills/README.md`.

N'y placer que des skills **réellement transverses au PM** ; un skill propre à un autre
domaine (sécurité, etc.) vit dans le repo de ce domaine.

**Créer un skill PM** : poser le `SKILL.md` directement dans `skills/<nom>/` (versionné),
et son éventuel script dans `scripts/pm-<entité>-<action>.py` (comme les autres `pm-*.py`),
référencé en relatif depuis le `SKILL.md`. **Jamais** dans le dossier skills perso
(`~/.claude/skills/`, repo `claude-skills`) — c'est ce repo PM qui révisionne et distribue
les skills de l'outillage. Lancer ensuite `scripts/pm-skills-sync.py` pour créer le symlink
qui le rend invocable, et l'ajouter à `skills/README.md`. L'état purement instance-local
qu'un skill produit (worklogs de session, caches) reste **hors repo** (ex: `~/.claude/...`).

## Docs vivantes du repo PM (`Changelog.md` + `README.md`)

Le repo PM se documente **au fil des livraisons**, pas en rattrapages (RM2250 :
deux mois de retard résorbés d'un bloc — à ne pas reproduire) :

- **`Changelog.md` (système)** : toute livraison qui change la **surface du
  système** — nouvel outil/skill, nouveau flux (statuts, envs, cockpit), changement
  de comportement d'un outil existant — ajoute sa ligne à l'entrée jalon courante
  (ou en ouvre une) **dans la même MR** que le code. Niveau de détail : le **jalon
  et son pourquoi** avec RM-ids, pas le commit-par-commit (le détail vit dans les
  tickets ; les normes dans `norms/CHANGELOG.md`).
- **`README.md`** : à retoucher quand l'installation, la structure du repo ou les
  points d'entrée changent. **Jamais de valeur qui rouille** (numéro de version,
  compte d'outils…) : pointer les sources vivantes (`norms/VERSION`, `scripts/`).
- Ces mises à jour font partie de la **livraison** (même esprit que le CHANGELOG
  projet à chaque merge dans main) — un reviewer peut refuser une MR « surface »
  sans sa ligne de Changelog.

### Développement du PM — doc vivante à quatre cibles (RM2595)

Le contrat « docs vivantes » ci-dessus est le **contrat de développement du PM**.
Il porte sur **quatre cibles** : toute livraison qui change la surface concernée
met à jour, **dans la même MR** que le code, la doc correspondante — un reviewer
peut refuser une MR « surface » dont la doc n'a pas suivi.

| Cible | Se met à jour quand… | Où |
|---|---|---|
| `Changelog.md` | la **surface système** change (outil, skill, flux statuts/envs/cockpit) | entrée jalon courante (`[Unreleased]` ou nouvelle) |
| `README.md` | **installation / structure / points d'entrée** changent | section concernée (pas de valeur qui rouille) |
| **Aide cockpit** (RM2593) | une **surface UTILISATEUR du cockpit** change (panneau, action, geste) | page `deploy/karl-agent/cockpit/help/<topic>.md` |
| **Doc développeur** (RM2594) | l'**architecture, les flux ou la boucle de dev** changent | `DEVELOPMENT.md` (relie ; pointe les sources vivantes) |
| **CDC vivant du projet** (RM3043) | une **décision / un arbitrage** est rendu en séance, une **question** reste ouverte, une **fonctionnalité** est livrée, prise ou planifiée | `docs/cdc-<prefix>-90-decisions.md` (D/C), `-99-questions-ouvertes.md` (Q), `-91-vrac.md` (N verbatim) ; fonctionnalités : `pm-cdc-features --sync --build` (registre yml → chapitre 10 généré, `--check` vert à la livraison). Modèle AtomBox (`modele-cdc/`) ; bouton 📋 CDC du cockpit |

Principe commun (le CDC vivant inclus) : **pas de rattrapage** (RM2250), pas de valeur qui rouille
(pointer `norms/VERSION`, `scripts/`, le command-catalog), niveau **jalon** et non
commit-par-commit (le détail vit dans les tickets).

### Licence du code et contributions (RM3029)

Le code du repo PM est publié sous **GPL-3.0-or-later** (`LICENSE` à la racine, décision
iProspective du 2026-09-07). Toute contribution — humaine ou d'agent — est faite **sous cette
même licence** ; une dépendance ajoutée doit lui être compatible (MIT, BSD, Apache-2.0, LGPL,
MPL-2.0 le sont ; une licence non libre ou incompatible se refuse en revue). Les données de
projets (dépôt privé `*-core`) ne sont pas couvertes. Un nouveau projet ou dépôt choisit sa
licence à la naissance (RM3030, `pm-project-new` / `pm-repo-new`).

### Changements sans ticket (RM2644)

Certains changements du repo PM **ne demandent pas de ticket Redmine** : le ticket y
coûterait plus cher que le changement lui-même, et n'apprendrait rien à personne.

| Sans ticket | Avec ticket |
|---|---|
| ajout d'un terme au **glossaire du cockpit** (`GLOSSARY`) | tout changement de **comportement** d'un outil |
| correction de coquille / reformulation sans changement de sens | toute évolution de **surface** (outil, flux, statuts, envs, cockpit) |
| — | toute modification de **NORMS** |

**Ce qui ne change pas : la MR.** Les branches d'intégration et de prod restent
protégées (tripwire #3) — « sans ticket » ne veut pas dire « push direct ». Ce qui
tombe, faute d'objet, c'est ce qui s'accroche au ticket : CF Redmine *GIT Branche* /
*GIT PR*, `git.mr_urls` du frontmatter, transition de statut.

Outil : **`pm-mr create --no-ticket --title "…"`**. Il exige un titre (le titre par
défaut est `RM<id> — <branche>`, qui n'existe pas ici), refuse `--status`, refuse un
`rm_id` passé en même temps, et **refuse une branche préfixée `<id>-`** — dans ce
mode, une telle branche trahit un ticket oublié, pas un changement ticketless. Nommer
la branche par son sujet (`glossaire-one-off`).

En cas de doute : **prendre un ticket**. La dispense couvre ce qui est trivial et
réversible, pas ce qui mérite d'être retrouvé plus tard.

## Les normes après une compaction (RM3071)

Une compaction remplace la conversation par un résumé : la tâche y survit, les normes non. L'agent qui
continue ne travaille plus avec le KERNEL mais avec le souvenir qu'il en a — et les garde-fous tombent un
par un, sans que rien ne le signale.

Le système le répare lui-même, pour **tous les projets**, sans dépendre de la vigilance de l'agent :

- `mmi-pm norms-recall` rend le KERNEL à réinjecter (la version dense de `norms/runtime/` si elle existe,
  la source humaine sinon), précédé de la raison de son retour ;
- il est câblé dans le bloc de hooks canonique de `pm-claude-hooks-sync` sur `SessionStart` de matcher
  `compact|resume` : sa sortie est versée au contexte de la session qui reprend. Elle n'est donc **pas**
  silencée, contrairement aux autres hooks PM ;
- il est posé à l'installation comme les autres hooks, et re-posé à chaque `pm-core-update` (étape 7) sur
  le profil de chaque utilisateur ; `pm-claude-hooks-sync --check` le voit manquer.

Un hook qui n'a rien à dire se tait et rend 0 : il ne casse jamais la session qui reprend. Si le rappel
n'arrive pas, l'agent relit le KERNEL de lui-même avant d'agir — c'est écrit dans le KERNEL et dans
`agents/worker-common.md`.

## Versionning des normes

| Type | Exemple | Règle |
|---|---|---|
| Majeur | `1.0 → 2.0` | Changement breaking — snapshot archivé dans `archive/` |
| Mineur | `1.0 → 1.1` | Ajout rétrocompatible — snapshot archivé dans `archive/` |
| Patch | `1.1 → 1.1.1` | Clarification — CHANGELOG suffit, pas d'archive |

### Procédure de mise à jour (anti-collision multi-sessions)

Plusieurs agents/sessions partagent le **même filesystem** (un seul `NORMS.md`) et la
**même branche de travail** du repo PM. Une mise à jour de NORMS (choix du numéro de
version **ET** commit) peut donc entrer en collision avec une mise à jour parallèle.
**Avant** de bumper la version et **avant** de committer, vérifier qu'aucune mise à
jour concurrente n'a déjà engagé le même numéro de version — sous l'une de ces formes :

1. **Update non commité** (sur le disque partagé) : une autre session a peut-être déjà
   édité `NORMS.md`/`CHANGELOG.md` sans committer. → **Relire `schema_version` sur
   disque juste avant de choisir le numéro cible** (ne pas se fier à la valeur lue en
   début de session) et inspecter l'état de travail (`git status`, diff non commité).
   Le numéro cible doit être strictement supérieur à la version réellement présente.
2. **Commit non pull** (côté remote ou autre clone) : un bump peut exister dans un
   commit pas encore récupéré. → **`git fetch` puis vérifier que la branche n'est pas
   en retard** ; faire un `pull --rebase` si besoin avant de committer. Au push,
   résoudre délibérément tout conflit sur la ligne `schema_version` / le `CHANGELOG`
   (ce sont les points de conflit attendus).

Règles de réduction de la fenêtre de course :
- Le **bump de version est la dernière étape** d'édition, suivi d'un **commit
  immédiat** (ne pas laisser traîner un bump non commité).
- Si la version sur disque ≠ celle lue au démarrage de la tâche → **stop**, réconcilier
  (rebaser, renuméroter) avant de poursuivre ; ne jamais bumper à l'aveugle.

### Budget de contexte par rôle (RM1943)

Le KERNEL + les modules **préchargés** par un rôle constituent le contexte
**toujours-chargé** de chaque session de ce rôle — payé à chaque démarrage. C'est
le poste que la factorisation NORMS (RM1922) optimise ; il ne doit pas re-gonfler
en douce.

- **Mesurer** : `scripts/pm-context-budget.py --all-roles` (détail d'un rôle :
  `--role <r>` ; cascade d'un projet réel : `--entity E --project P` ; référence
  d'avant la factorisation : `--before`). Estimation octets/3,6 (le tokenizer réel
  n'est pas accessible hors API — ordre de grandeur, pas valeur exacte).
- **Plafond** : `pm.config.yml :: context.budget_tokens` (`default` + override par
  rôle). `pm-norms-doctor` échoue si un rôle dépasse (invariant anti-régression).
- **Conséquence pratique** : ajouter un module au **préchargement** d'un rôle
  (en-tête `> … **Préchargé par :** …`) augmente son contexte fixe. Ne précharger
  qu'un module **réellement utilisé à chaque session** du rôle ; sinon le laisser
  **à la demande** (ouvert via son déclencheur KERNEL). Premier levier de réduction
  si un plafond est atteint : retirer un module du préchargement le plus lourd
  (à ce jour `status-workflow`, ~5,6k).
