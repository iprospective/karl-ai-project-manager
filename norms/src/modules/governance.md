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
