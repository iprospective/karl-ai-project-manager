---
schema_version: "1.1"
updated: 2026-04-27
---

# Normes de gestion des tâches — v1.1

## Configuration globale

```yaml
gitlab:
  instance: https://gitlab.iprospective.fr
  ssh: gitlab@repos.iprospective.fr

redmine:
  instance: # défini par projet dans project.md
```

## Structure des dossiers

```
project-management/
  norms/
    NORMS.md                          # version courante (ce fichier)
    CHANGELOG.md                      # historique des évolutions
    archive/                          # snapshots des versions majeures
  projects/
    {nom-projet}/
      project.md
      tasks/
        RM{id}_{titre-kebab}.md       # tâche
        RM{id}_{titre-kebab}.log.md   # journal append-only
  templates/
    task.md
    project.md
```

## Nommage des fichiers

| Élément | Format |
|---|---|
| Tâche | `RM{id}_{titre-en-kebab-case}.md` |
| Journal | `RM{id}_{titre-en-kebab-case}.log.md` |
| Projet | `project.md` à la racine du dossier projet |

## Schéma frontmatter — Tâche

Voir [templates/task.md](../templates/task.md) pour le template complet.

### Champs obligatoires
`schema_version`, `redmine_id`, `title`, `type`, `creator`, `status`, `priority`, `created`

### Champs conditionnels
- `bug.*` — uniquement si `type: bugfix`
- `git.*` — si développement impliqué
- `test_url` — si environnement de test disponible
- `deploy_actions` — si déploiement nécessaire
- `close_reason` — obligatoire quand `status: ferme`

## Machine d'états

```
[a_etudier_chiffrer]
        │ estimation lancée
        ▼
[etude_chiffrage_en_cours]
        │ approuvé                  │ abandonné / hors périmètre
        ▼                           ▼
   [a_faire]                    [ferme]
        │ démarrage
        ▼
   [en_cours] ◄──────────────────────────┐
        │ soumis                         │ corrections faites
        ▼                                │
[a_tester_verifier]                      │
        │ problèmes trouvés              │
        ├──────────────► [a_corriger] ───┘
        │ validé
        ▼
    [ferme]
```

Règle : **toute transition vers `ferme` requiert un `close_reason`.**

### Transitions valides

| De | Vers | Condition |
|---|---|---|
| `a_etudier_chiffrer` | `etude_chiffrage_en_cours` | `assigned_to` renseigné |
| `etude_chiffrage_en_cours` | `a_faire` | `estimate.*` complet |
| `etude_chiffrage_en_cours` | `ferme` | `close_reason` requis |
| `a_faire` | `en_cours` | — |
| `en_cours` | `a_tester_verifier` | — |
| `en_cours` | `a_etudier_chiffrer` | périmètre modifié |
| `a_tester_verifier` | `a_corriger` | note dans journal |
| `a_tester_verifier` | `ferme` | `close_reason: resolu` |
| `a_corriger` | `en_cours` | — |
| `* (tout état)` | `ferme` | `close_reason` requis |

## Valeurs énumérées

### type
`audit` | `feature` | `bugfix` | `refactoring` | `documentation` | `security` | `performance` | `infrastructure` | `research` | `maintenance` | `assistance`

### status
`a_etudier_chiffrer` | `etude_chiffrage_en_cours` | `a_faire` | `en_cours` | `a_tester_verifier` | `a_corriger` | `ferme`

### priority
`low` | `normal` | `high` | `urgent`

### close_reason
`resolu` | `abandonne` | `doublon` | `wont_fix` | `invalide` | `hors_perimetre`

### bug.reproducibility
`always` | `often` | `sometimes` | `rarely` | `never`

### estimate.difficulty
`low` | `medium` | `high` | `critical`

### pistes.type
`automation` | `amélioration` | `sécurité` | `performance` | `intégration` | `documentation`

### pistes.effort
`low` | `medium` | `high`

### roi.immediate_benefit / roi.monthly_benefit
`1` (négligeable) → `5` (critique)

## Journal (fichier .log.md)

Format append-only — ne jamais modifier rétroactivement. Chaque entrée :

```markdown
## 2026-04-26T14:32 — agent-scraper (claude-sonnet-4-6)
Tokens : 3 200 | Durée : 15 min

Résumé de ce qui a été fait...
```

## Collaboration multi-agents

### Principe fondamental

**Redmine est le mutex. Les fichiers MD sont le contexte de travail.**

L'assignation d'un ticket Redmine à un agent lui confère la **propriété exclusive** du fichier MD correspondant. Aucun autre agent ne doit écrire dans ce fichier tant que l'assignation est active.

L'inférence LLM est déjà distribuée par nature (appels API vers Anthropic). Ce qui doit être coordonné, c'est uniquement l'accès aux fichiers.

### Rôles des agents

**Orchestrateur**
- Un agent coordinateur unique par périmètre actif
- Surveille les tickets en attente (`a_faire`) dont les dépendances sont satisfaites
- Assigne les tickets aux workers via l'API Redmine (opération atomique)
- Seul écrivain sur les fichiers de tâches parentes (à tous les niveaux)
- Met à jour `completion_pct` des parents quand leurs enfants terminent (propagation bottom-up)
- Déclenche le reviewer quand une tâche passe en `a_tester_verifier`
- Route les tickets vers le bon worker selon le champ `type`

**Workers (agents spécialisés)**

| Type de tâche | Agent recommandé |
|---|---|
| `feature` / `refactoring` | agent-dev |
| `bugfix` | agent-debug |
| `audit` / `research` | agent-analyst |
| `documentation` | agent-writer |
| `security` / `performance` | agent-specialist |

- Propriétaire exclusif de leur fichier de tâche assignée
- Lecture seule sur tous les autres fichiers MD
- Append-only sur tous les `.log.md`

**Reviewer**
- Déclenché par l'orchestrateur sur `a_tester_verifier`
- Lit le fichier de tâche + le `.log.md` + les critères d'acceptation
- Valide → `ferme` avec `close_reason: resolu`
- Rejette → `a_corriger` avec note obligatoire dans le `.log.md`

### Règles d'écriture

| Fichier | Orchestrateur | Worker assigné | Autres workers | Reviewer |
|---|---|---|---|---|
| `RM{id}.md` (tâche assignée) | lecture | **R+W** | lecture | lecture |
| `RM{id}.md` (tâche parente) | **R+W** | lecture | lecture | lecture |
| `RM{id}.log.md` | append | append | lecture | append |
| `project.md` | **R+W** | lecture | lecture | lecture |
| `NORMS.md` | lecture | lecture | lecture | lecture |

### Protocole de prise en charge d'une tâche

```
1. Orchestrateur lit les tickets Redmine status=a_faire
2. Pour chaque ticket éligible :
   a. Vérifie que tous les tickets dans depends_on sont ferme
   b. Sélectionne le worker adapté au type de tâche
   c. Assigne le ticket Redmine au worker via API (atomique)
      → succès   : l'agent est propriétaire, continuer
      → conflit  : ticket déjà pris, passer au suivant
3. Worker reçoit l'assignation
4. Worker lit son fichier RM{id}.md
5. Worker met à jour le frontmatter :
   - status: en_cours
   - status_history: + nouvelle entrée (at, by, model)
   - updated: timestamp courant
6. Worker travaille, appende ses logs dans RM{id}.log.md
7. À la fin, worker met à jour son fichier :
   - completion_pct, outputs, updated, status_history
8. Worker passe le ticket Redmine en a_tester_verifier
9. Orchestrateur détecte le changement, déclenche le reviewer
10. Reviewer approuve ou renvoie en a_corriger
11. Si approuvé : orchestrateur propage la completion au parent
```

### Sous-tâches multi-niveaux

Les sous-tâches s'imbriquent sur autant de niveaux que nécessaire. La règle est uniforme : **l'orchestrateur est le seul écrivain sur toute tâche ayant des enfants**, quel que soit le niveau.

```
RM1000  (niveau 0 — racine)        → orchestrateur
  ├── RM1001  (niveau 1 — parent)  → orchestrateur
  │     ├── RM1002  (niveau 2)     → agent-A
  │     └── RM1003  (niveau 2)     → agent-B
  └── RM1004  (niveau 1 — parent)  → orchestrateur
        ├── RM1005  (niveau 2)     → agent-C
        └── RM1006  (niveau 2)     → agent-D
```

**Propagation du `completion_pct` :**
- Une leaf termine → orchestrateur recalcule le `completion_pct` de son parent immédiat
- Si le parent est complet → orchestrateur propage au grand-parent
- Propagation bottom-up jusqu'à la racine

**Règle :** un nœud parent passe en `ferme` uniquement quand **tous ses enfants directs** sont `ferme`.

**Parallélisme :** les agents travaillant sur des leaves de branches différentes s'exécutent simultanément sans coordination entre eux. Seul l'orchestrateur synchronise au niveau des parents.

### Protocole optimistic locking

Filet de sécurité contre les écritures simultanées accidentelles. Doit se déclencher rarement si les règles de propriété sont respectées.

```
1. Agent lit le fichier, note la valeur courante de updated (T1)
2. Agent prépare ses modifications
3. Agent relit le champ updated avant d'écrire
4. Si updated ≠ T1 → collision détectée → re-lire le fichier et recommencer
5. Si updated = T1 → écrire et mettre updated à T2 (timestamp courant)
```

Ce protocole s'applique à tous les fichiers `.md` (jamais aux `.log.md` qui sont append-only).

### Règles du journal (.log.md)

- **Append-only** : on n'efface jamais, on n'édite jamais une entrée existante
- Tout agent peut appender, même en lecture seule sur la tâche
- En cas d'écriture simultanée, l'ordre des entrées n'est pas garanti — c'est acceptable
- Pas d'optimistic locking sur les `.log.md` (append = pas de perte de données)

Format imposé pour chaque entrée :

```markdown
## 2026-04-27T14:32 — agent-dev (claude-sonnet-4-6)
Tokens : 3 200 | Durée : 15 min

Résumé de ce qui a été fait, décisions prises, problèmes rencontrés.
```

---

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

Chaque serveur a un clone local du repo GitLab. Les agents travaillent sur des branches dédiées. Git gère la synchronisation et détecte les conflits au merge. C'est la solution la plus robuste et scalable.

```
GitLab (source de vérité)
        │
        ├── main                          ← tâches validées, état stable
        ├── agent/srv-A/RM1234-feature    ← Worker A (serveur A)
        ├── agent/srv-B/RM1235-bugfix     ← Worker B (serveur B)
        └── agent/srv-C/RM1236-audit      ← Worker C (serveur C)
```

**Cycle de vie d'une tâche en V2 :**
```
1. Orchestrateur crée la branche agent/{server}/{RM{id}-titre} sur GitLab
2. Worker checkout la branche sur son serveur local
3. Worker travaille, commit régulièrement (au moins à chaque changement de status)
4. Worker crée une MR vers main quand la tâche passe en a_tester_verifier
5. Reviewer valide la MR
6. Merge → état stable dans main → tâche ferme
```

**Avantages :** distribution réelle sans NFS, historique complet des changements, détection de conflits native, intégration naturelle avec le workflow GitLab déjà prévu.

### Choix selon le contexte

| Situation | Architecture |
|---|---|
| Démarrage, 1 serveur | **V1** |
| Ajout rapide de 1-2 serveurs | **V1.5** (NFS) |
| Scalabilité et robustesse | **V2** (Git/branches) |
| Très grand volume, état centralisé | V3 — base de données (future) |

---

## Versionning des normes

| Type | Exemple | Règle |
|---|---|---|
| Majeur | `1.0 → 2.0` | Changement breaking — snapshot archivé dans `archive/NORMS_v{M}.0.md` |
| Mineur | `1.0 → 1.1` | Ajout rétrocompatible — CHANGELOG suffit |
| Patch | `1.1 → 1.1.1` | Clarification — CHANGELOG suffit |
