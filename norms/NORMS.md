---
schema_version: "1.5.2"
updated: 2026-05-13
---

# Normes de gestion des tâches — v1.5.2

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

paths:
  projects: ${PROJECTS_PATH}   # chemin absolu vers le repo projects/
```

## Structure des dossiers

### Repo project-management (système, public)

```
project-management/
  norms/
    NORMS.md                          # version courante (ce fichier)
    CHANGELOG.md                      # historique des évolutions
    archive/                          # snapshots de toutes les versions
  templates/
    client.md                         # template client
    project.md                        # template projet
    task.md                           # template tâche (skeleton)
    RM9999_*.md                       # exemple complet pour CI
  agents/
    worker-common.md                  # règles communes des workers
    worker-{role}.md                  # rôles spécifiques
    orchestrateur.md
    reviewer.md
    summarizer.md                     # génération auto des Changelog/Pistes/Remarques
  scripts/
    validate-task.py
    priority.py                       # ordonnancement par ROI
    pm-dashboard.py                   # CLI dashboard (statuts, ROI, en cours, activité)
    redmine-test.py                   # test de connexion API Redmine
    redmine-fetch-task.py             # fetch ticket Redmine → génère le MD
    redmine-fetch-updates.py          # récupère les nouveautés depuis le dernier check
    redmine-post-note.py              # poste une note (+ statut + assignation) sur un ticket
    invoke.md
    cron.example.sh
```

### Repo projets (privé, gitignored dans le repo PM)

```
projects/                             # ai-projects (repo séparé)
  README.md
  clients/
    {client-slug}/
      client/                         # cahier des charges client (multi-fichiers)
        overview.md                   # OBLIGATOIRE — frontmatter + sommaire
        hosting.md                    # aspect — optionnel
        contracts.md                  # aspect — optionnel
        ...                           # tout aspect pertinent
      memory/                         # mémoire structurée (écrite par agents)
      Changelog.md                    # AUTO — activité agrégée
      Pistes.md                       # AUTO — idées non décidées
      Remarques.md                    # AUTO — observations factuelles
      projects/
        {projet-slug}/
          project/                    # cahier des charges projet (multi-fichiers)
            overview.md               # OBLIGATOIRE — frontmatter + sommaire
            hosting.md                # aspect — optionnel
            stack.md
            data-model.md
            workflows.md
            audience.md               # exemples — uniquement les aspects pertinents
            ...
          memory/                     # mémoire spécifique projet
          Changelog.md                # AUTO
          Pistes.md                   # AUTO
          Remarques.md                # AUTO
          tasks/
            RM{id}_{titre-kebab}.md
            RM{id}_{titre-kebab}.log.md
```

### Workspace projet et symlink `mmi-pm`

Chaque projet a **deux emplacements** distincts mais liés :

| Emplacement | Contenu | Repo git |
|---|---|---|
| `/zfs/workspaces/{P}/` | Code source du projet | repo de code (ex: `iprospective/dev/{P}`) |
| `$PROJECTS_PATH/clients/{C}/projects/{P}/` | Cahier des charges, tâches, mémoire | `ai-projects` |

Pour faciliter le travail conjoint code + tâches, un **symlink `mmi-pm`** dans le workspace
projet pointe vers le dossier PM centralisé :

```
/zfs/workspaces/{P}/mmi-pm → $PROJECTS_PATH/clients/{C}/projects/{P}/
```

**Création :**
```bash
cd /zfs/workspaces/{P}
ln -s "$PROJECTS_PATH/clients/{C}/projects/{P}" mmi-pm
```

**Bénéfices :**
- Un agent travaillant dans le workspace voit code ET tâches/docs (`mmi-pm/project/`, `mmi-pm/tasks/`)
- Un seul dossier de travail pour l'agent — pas de saut entre arbres distants
- La centralisation est préservée (l'orchestrateur scanne `$PROJECTS_PATH` directement)

**Résolution de chemins cross-tree** (ex: cascade vers le client) :
Ne pas utiliser `mmi-pm/../../` (résolution logique non fiable des symlinks). Utiliser
`$PROJECTS_PATH` + le champ `client:` du frontmatter de `project/overview.md` :

```bash
CLIENT_DIR="$PROJECTS_PATH/clients/${client_slug}"
```

### Aspects — cahier des charges dynamique

Le **cahier des charges** d'un client ou d'un projet est éclaté en plusieurs fichiers
(aspects) dans le dossier `client/` ou `project/`. Cette approche évite le fichier
monolithique illisible et permet d'enrichir progressivement la connaissance du périmètre.

**Règles :**
- `overview.md` est **obligatoire** — il porte le frontmatter et un index des aspects
- Tout autre fichier est **optionnel** — sa présence indique que l'aspect est documenté
- L'agent qui charge le contexte lit **tous** les fichiers du dossier `project/` (et `client/`)
- Les templates d'aspects sont dans `templates/aspects/{domaine}/{aspect}.md`

**Cascade des aspects :**
Un aspect peut exister au niveau client ET au niveau projet. L'agent lit les deux.
Le projet précise/surcharge le client sur les points en contradiction.

Exemple :
- `clients/{C}/client/hosting.md` : "Tous nos sites sont hébergés chez OVH par défaut"
- `clients/{C}/projects/{P}/project/hosting.md` : "Ce projet est sur AWS pour des raisons spécifiques"
→ Pour ce projet, l'agent applique AWS (override).

## Cascade et héritage

Le système suit une cascade à 3 niveaux : **client → projet → tâche**.

**Règles :**
- Par défaut, les valeurs d'un niveau parent sont héritées par tous ses enfants
- Un niveau enfant peut **surcharger** une valeur en la redéfinissant explicitement
- Les sections de texte (Description, Structure...) ne se surchargent pas — elles s'additionnent

**Champs candidats à l'héritage :**
- `team`, `defaults.priority`, `gitlab.group`, `gitlab.default_branch`
- `redmine.instance`, contraintes globales

**Lecture du contexte par un agent (worker, summarizer, reviewer) :**
```
1. Système    : NORMS.md + agents/worker-common.md + agents/worker-{role}.md
2. Client     : clients/{C}/client.md + memory/*.md
3. Projet     : clients/{C}/projects/{P}/project.md + memory/*.md
4. Tâche      : clients/{C}/projects/{P}/tasks/RM{id}_*.md + .log.md
```

Chaque niveau **complète** ou **surcharge** le précédent selon les règles ci-dessus.

## Fichiers auto-générés (écrits par l'agent summarizer)

| Fichier | Niveau | Contenu | Source |
|---|---|---|---|
| `Changelog.md` | client + projet | Activité datée (tâches fermées, étapes franchies) | Trigger événementiel sur `ferme` |
| `Pistes.md` | client + projet | Idées non décidées capitalisées | Agrège les `pistes[]` des tâches |
| `Remarques.md` | client + projet | Observations factuelles des agents (patterns, anomalies) | Extraits des `.log.md` |
| `client.md ## Structure` | client | Comment ce client opère, ses processus | Agrège observations long terme |
| `project.md ## Structure` | projet | Comment ce projet est architecturé, ses conventions | Agrège observations long terme |

## Ordonnancement par ROI

Script `scripts/priority.py` qui calcule pour chaque tâche `a_faire` :

```
score = (immediate_benefit + monthly_benefit * 12) * priority_weight / max(estimate.time_minutes, 1)
```

Avec `priority_weight = {low: 0.5, normal: 1, high: 2, urgent: 4}`.

Filtre : tâches `a_faire` dont toutes les `depends_on` sont `ferme`.
Sortie : top N tâches triées par score décroissant, par client/projet ou global.

## Nommage des fichiers

| Élément | Format |
|---|---|
| Tâche | `RM{id}_{titre-en-kebab-case}.md` |
| Journal | `RM{id}_{titre-en-kebab-case}.log.md` |
| Overview projet | `project/overview.md` |
| Overview client | `client/overview.md` |

## Lien Redmine ↔ MD (obligatoire)

Toute entité du système (tâche, projet) **doit** être reliée à son équivalent Redmine.
Cette règle est vérifiée par le validateur.

### Tâche

- `redmine_id: <int>` est **obligatoire** dans le frontmatter
- Le nom de fichier `RM{id}_{titre}.md` **doit correspondre** à `redmine_id`
  (cohérence vérifiée par le validateur)
- Pas de tâche MD sans ticket Redmine préexistant

### Projet

- `redmine.project_id: <slug>` est **obligatoire** dans `project/overview.md`
- `redmine.subprojects: [slug, slug, ...]` est optionnel — liste les sous-projets
  Redmine rattachés (utile quand plusieurs sous-projets concernent ce même projet MD)

### Workflow multi-tour (reprise après notes du demandeur)

Quand un ticket revient à un worker (réattribution, ou statut passe à `a_corriger`),
le worker doit ne traiter que les **nouveautés** depuis sa dernière vue du ticket.

Champs du frontmatter de la tâche :
- `redmine_last_journal_id: <int>` — id du dernier journal Redmine consulté
- `redmine_last_checked_at: <str iso>` — timestamp du dernier check

Protocole de reprise :
1. `scripts/redmine-fetch-updates.py --issue <id>` → affiche tous les journaux
   postérieurs à `redmine_last_journal_id`, et met à jour ce champ
2. Lire les nouvelles notes + changements d'attributs (status, assignation, priorité…)
3. Décider : corrections à faire ? livrables à compléter ? ticket déjà résolu ?
4. Appliquer le travail demandé selon le protocole worker standard
5. Resoumettre via `redmine-post-note.py --norms-status a_tester_verifier` (qui
   réattribue automatiquement au demandeur)

Le champ `redmine_last_journal_id` est initialisé par `redmine-fetch-task.py` à la
**dernière entrée existante** au moment du fetch, pour que le worker ne traite que
ce qui se passe **après** sa prise en charge.

**Persistance dans le journal** : `redmine-fetch-updates.py` appende chaque nouveau
journal Redmine récupéré au fichier `.log.md` de la tâche (append-only, conforme
NORMS). Format d'entrée :

```markdown
## YYYY-MM-DDTHH:MM — Redmine #<journal_id> — <auteur Redmine>
Source : Redmine (sync via redmine-fetch-updates)

Changements :
- `field` : `old` → `new`
- ...

Note (verbatim) :
> ligne 1
> ligne 2
```

Le worker peut ainsi retrouver l'historique complet des échanges (côté Redmine ET
côté agent) en relisant simplement le `.log.md`, sans avoir à re-fetcher l'API.

### Synchronisation des statuts MD ↔ Redmine (obligatoire)

**Tout changement de `status` dans le frontmatter d'une tâche doit être répercuté
sur le ticket Redmine correspondant**, dans le même cycle de travail.

L'agent (ou l'orchestrateur) qui modifie le `status` MD doit :
1. Mettre à jour le frontmatter (`status`, `status_history`, `updated`)
2. Appender l'événement dans `.log.md`
3. Poster une note Redmine + changer le `status_id` correspondant
   (typiquement via `scripts/redmine-post-note.py --norms-status <statut>`)

**Règle d'attribution Redmine** :
- Passage en `a_tester_verifier` → ré-attribuer le ticket au **demandeur** (auteur Redmine)
  pour qu'il puisse tester. `redmine-post-note.py --norms-status a_tester_verifier` le fait
  automatiquement (équivaut à `--assign-to author`).
- Passage en `a_corriger` → ré-attribuer au **worker** précédent (manuellement pour
  l'instant via `--assign-to <id>`, automatisé quand l'orchestrateur sera en place).
- Passage en `ferme` → conserver l'attribution courante.

**Mapping NORMS → Redmine (instance iprospective)** :

| NORMS | Redmine | id |
|---|---|---|
| `a_etudier_chiffrer` | A étudier / Qualifier | 8 |
| `etude_chiffrage_en_cours` | Etude en cours | 14 |
| `a_faire` | A Faire | 12 |
| `en_cours` | En cours | 2 |
| `a_tester_verifier` | A tester/vérifier | 9 |
| `a_corriger` | A corriger | 11 |
| `ferme` (`close_reason: resolu`) | Résolu/Fermé | 5 |
| `ferme` (`close_reason: abandonne`) | Abandonné | 10 |
| `ferme` (`close_reason: wont_fix` / `hors_perimetre`) | Rejeté | 6 |
| `ferme` (`close_reason: invalide` / `doublon`) | Pas un bug / Déjà existant | 7 |

### Flux de création de tâches (v1.5.0)

Deux flux supportés :

**a) Création depuis Redmine** (workflow humain ou agent)
1. Un humain (ou un agent) crée le ticket dans Redmine et l'assigne à un agent IA
2. L'orchestrateur détecte l'assignation, génère `clients/{C}/projects/{P}/tasks/RM{id}_*.md`
3. Le worker assigné prend la tâche en charge

**b) Création depuis CLI dans le workspace projet** (à implémenter — voir [TODO/003](../TODO/003-pm-cli.md))
1. Depuis `/zfs/workspaces/{P}`, l'utilisateur lance `pm task create --type ... --title "..."`
2. Le script crée le ticket Redmine, récupère l'ID
3. Génère le fichier MD dans `mmi-pm/tasks/RM{id}_*.md`
4. Commit + push automatique

Le sens inverse pur (MD → Redmine sans ticket préexistant) n'est pas implémenté en
v1.5 — voir [PISTES.md](../PISTES.md).

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
`audit` | `feature` | `bugfix` | `refactoring` | `documentation` | `security` | `performance` | `infrastructure` | `database` | `design` | `research` | `maintenance` | `assistance`

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

| Type de tâche | Agent |
|---|---|
| `feature` / `bugfix` / `refactoring` / `security` / `performance` | worker-dev |
| `audit` / `research` / `documentation` / `assistance` / `maintenance` | worker-analyst |
| `database` | worker-db |
| `infrastructure` | worker-infra |
| `design` | worker-design |

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
| Majeur | `1.0 → 2.0` | Changement breaking — snapshot archivé dans `archive/` |
| Mineur | `1.0 → 1.1` | Ajout rétrocompatible — snapshot archivé dans `archive/` |
| Patch | `1.1 → 1.1.1` | Clarification — CHANGELOG suffit, pas d'archive |
