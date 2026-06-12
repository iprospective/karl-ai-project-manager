# CDC — Restructuration de l'écosystème workspaces + éclatement des données PM

| | |
|---|---|
| **Statut** | DRAFT — à valider par Mathieu |
| **Date** | 2026-06-12 |
| **Rédaction** | karl (session interactive avec Mathieu) |
| **Tickets sources** | RM1887, RM1885, RM1834, RM1769, RM1892, RM1883, RM1837, RM1906, RM1922/1923/1940 |
| **Documents liés** | ADR 0001 (à amender, cf. § 2.4), `norms/RESTRUCTURING-CDC.md` (RM1922), `norms/MAINTAINING.md` |

---

## 1. Objet et drivers

Restructurer l'ensemble `/zfs/workspaces` + le système PM pour atteindre quatre objectifs :

- **D1 — Multi-tenant client-facing (RM1906, driver principal)** : pouvoir déployer un
  orchestrateur `karl-<client>` (ou une instance fédérée comme `hal`) dont le périmètre
  git est **réellement confiné par les droits GitLab** — au client entier, ou à un seul
  projet. Le confinement par les droits, pas par convention.
- **D2 — Versionnement fin** : chaque client et chaque projet versionnés indépendamment ;
  cloner un environnement restreint = cloner des workspaces, rien d'autre.
- **D3 — Multi-écrivains (RM1834)** : supprimer l'entremêlement des commits de sessions
  parallèles sur le monorepo de données (`ai-projects`), en distribuant la donnée PM
  par projet et en isolant les sessions par worktree.
- **D4 — Économie de ressources** : contexte par session (NORMS modulaire RM1922, budget
  d'abonnement Claude) et espace disque (bare repos partagés entre projets produit).

**Contrainte de séquencement posée par Mathieu** : la normalisation des workspaces
(chantier C2) se fait **avant** l'éclatement des données PM (chantier C3).

## 2. Décisions actées

Décisions prises et confirmées (sessions du 2026-06-09 et 2026-06-12) :

1. **Cloisonnement par les droits GitLab** (pas sparse-checkout, pas limitation
   conventionnelle au pull). Source : session 2026-06-09 (« A : Oui ») + RM1906.
2. **Grain de repo = projet ; grain de droits = groupe client OU repo projet.**
   La donnée PM d'un projet vit dans le repo de son workspace projet ; les droits se
   posent au niveau du groupe GitLab client (tout le client) ou d'un repo individuel
   (cas `hal` limité à un projet). Source : 2026-06-09 (« B : repos par projet ») +
   2026-06-12 (granularité double explicitée).
3. **Modèle 2 — co-location (workspace-centré)** : `.mmi-pm` cesse d'être un symlink et
   devient un **dossier réel committé** dans le repo du workspace projet. Côté outil PM,
   `projects/` devient une **vue gitignorée** (symlinks vers les dossiers clients).
   Dans un premier temps, le repo workspace projet peut ne tracker **que** `.mmi-pm/`.
   Source : 2026-06-12.
4. **Pas de submodules pour la donnée PM** (pointeurs = churn permanent sur donnée
   vivante ; `--init --recursive` échoue bruyamment sur les repos interdits).
   **Découverte dynamique via l'API GitLab** à la place (cf. § 3.5). Source : 2026-06-12.
5. **Cœur client** : données PM niveau client (`client/`, `memory/`, `projects_used/`)
   dans `<client>/.mmi-pm/`, committées dans un repo « client-core ». Source : 2026-06-12.
6. **Outil PM** : déménage vers `/zfs/workspaces/.mmi-pm-core/`, intégré en **submodule**
   du repo env racine (le submodule est justifié ici : repo outil à évolution lente,
   pointeur épinglé = version d'orchestrateur maîtrisée par instance). Source : 2026-06-12.
7. **Repo env racine `/zfs/workspaces`** : régulariser le `.git` existant (init sans
   commit) en repo « env » versionnant AGENTS.md/CLAUDE.md, le tooling commun et le
   submodule `.mmi-pm-core/` ; gitignore en **liste blanche**. Source : 2026-06-12.
8. **Environnements locaux standard par projet de dev** : un **bare repo** par projet +
   worktrees `dev/` et `test/` (réservés à l'humain) + `.worktrees/<ticket>` éphémères
   (sessions agent, RM1834). Les projets implémentant un produit (Dolibarr, PrestaShop…)
   partagent l'object store du produit via un **miroir bare commun + alternates**.
   Source : 2026-06-12.
9. **RM1834 = hybride A+B** : branche-par-tâche dans un worktree ; sur branche partagée,
   ne committer que ses propres modifs. Données + BDD partagées, avec outil de clonage
   de BDD à la demande. Emplacement : `.worktrees/` caché non versionné. RM1834 dépend
   de la nouvelle structure (relation #397). Source : 2026-06-09.
10. **RM1769 = navigation, pas montage** (les symlinks bidirectionnels restent un
    confort de navigation ; le montage canonique est la co-location). Source : ADR 0001.
11. **Validation des tickets** : introduire des critères « auto-validable » + un niveau
    de **risque**, qualifiés dans Redmine (CF à concevoir), avec possibilité de forcer
    l'auto-validation sur un ticket risqué ; traitement par lots ; l'agent-testeur
    (RM1879/1910) n'est pas systématiquement validateur de MEP. Source : 2026-06-12.

### 2.4 Mise à jour des documents de référence (dette à résorber en C0)

- **ADR 0001** dit encore « repo PAR CLIENT, option par-projet rejetée » : à amender →
  grain repo = projet / grain droits = groupe client (décision 2), modèle de montage =
  co-location (décision 3).
- Corps MD de **RM1887** et **RM1834** : reporter les décisions (aujourd'hui uniquement
  en notes Redmine + transcripts).

## 3. Architecture cible

### 3.1 Repo « env » racine `/zfs/workspaces`

```
/zfs/workspaces/                  ← repo env (régularisation du .git existant)
├── .gitignore                    ← liste blanche : « /* » ignoré + exceptions explicites
├── AGENTS.md                     ← VERSIONNÉ (résout le hors-git de RM1892)
├── CLAUDE.md → AGENTS.md         ← symlink versionné
├── .mmi-pm-core/                 ← SUBMODULE = outil PM (ex ai/project-management)
├── tooling/                      ← scripts/lib communs versionnés (à constituer)
├── calicote/  calyclay/  …       ← workspaces clients : IGNORÉS (chacun son repo)
└── 0-lib/ 1-securite/ 2-scripts/ … ← legacy, refactorisation ULTÉRIEURE (hors périmètre)
```

- Mise à jour d'une instance = `git pull && git submodule update --init --remote`.
- AGENTS.md versionné ⇒ le template `templates/workspace-AGENTS.md` du repo outil
  devient la source du fichier du repo env (ou est supprimé au profit de celui-ci).
- Les dossiers numérotés `0-*`…`9-*` seront refactorisés plus tard (souhait : ne voir
  à terme presque que les clients/projets actifs) — **hors périmètre de ce CDC**.

### 3.2 Workspace client

```
/zfs/workspaces/<client>/             ← repo « <client>-core »
├── .mmi-pm/                          ← données PM niveau client (committées)
│   ├── pm.yml                        ← marqueur { type: client, entity: <slug> }
│   ├── client/   memory/   projects_used/
├── .gitignore                        ← ignore les dossiers projets (et le reste)
├── <projet-1>/                       ← repo workspace projet (ignoré par le core)
└── <projet-2>/
```

- Le repo client-core ne contient **aucune liste de projets** : la liste vit dans le
  groupe GitLab (filtrée par les droits, cf. § 3.5).

### 3.3 Workspace projet — layout standard

```
/zfs/workspaces/<client>/<projet>/    ← repo « workspace projet »
├── .mmi-pm/                          ← données PM projet (committées) — phase 1 : seul contenu tracké
│   ├── pm.yml                        ← marqueur { type: project, entity: <c>, project: <p> }
│   ├── project/   memory/   tasks/   ← (tasks/RM<id>_*.md + .log.md)
├── .gitignore                        ← phase 1 : tout sauf .mmi-pm/
├── .repo.git/                        ← bare repo du code (ignoré)
├── dev/                              ← worktree HUMAIN (branche dev)
├── test/                             ← worktree HUMAIN (branche test/main)
└── .worktrees/                       ← worktrees éphémères par session/ticket (RM1834, ignorés)
    └── RM1234/
```

**Bare + worktrees (décision 8) :**

- `.repo.git` = clone bare du repo de code. Tous les environnements (dev, test,
  sessions) sont des `git worktree` de ce bare → instancier un env de session est
  quasi gratuit (pas de re-clone, objets partagés).
- Contrainte git assumée : une branche ne peut être checkée out que dans **un**
  worktree à la fois. Compatible avec NORMS (branche par ticket → un worktree par
  ticket) ; `dev/` et `test/` épinglent leurs branches longues.
- **Projets implémentant un produit** (Dolibarr, PrestaShop…) : le bare est cloné avec
  `--reference-if-able /zfs/workspaces/.products/<produit>.git` (alternates) → l'object
  store du produit n'est stocké **qu'une fois** pour tous les clients. Le jour des
  forks par client : seul le remote du bare change, les alternates restent valides.
- **BDD/data** : conformément à RM1834 — dossier de données partagé + liste de BDD de
  dev (une par défaut) + outil de clonage de BDD pour les tâches qui le requièrent.
  Les pools FPM/webserver continuent de pointer les chemins stables `dev/` et `test/`.

### 3.4 Miroirs produits partagés

```
/zfs/workspaces/.products/
├── dolibarr.git        ← miroir bare upstream (fetch périodique)
├── prestashop.git
└── …
```

- Rôle : source d'alternates pour les bares projets (§ 3.3). Append-only : **jamais de
  `gc`/`prune` agressif** sur ces miroirs (un prune casserait les emprunteurs) —
  config `gc.auto=0` + procédure documentée.
- Distinct des **entités PM produit** existantes (prestashop, redmine, roundcube,
  nextcloud…) qui, elles, suivent le schéma client/projet normal.

### 3.5 GitLab : namespace, droits, découverte

```
gitlab.iprospective.fr/clients/           ← groupe chapeau
└── <client>/                             ← 1 groupe par client  ← ACL « client entier »
    ├── <client>-core                     ← repo workspace client
    ├── <projet-1>                        ← repo workspace projet ← ACL « projet seul »
    └── <projet-2>
```

- **Droits** : membre du groupe `clients/<c>` → tout le client ; membre d'un seul repo
  → ce projet seul (cas `hal`). Le confinement RM1906/1908 s'appuie dessus.
- **Découverte dynamique — `pm-workspace-sync`** (nouveau script + skill) : interroge
  l'API GitLab (« repos du groupe `clients/<c>` visibles par MON token »), clone/pull
  chacun en place. Zéro warning (on ne tente jamais ce qu'on ne voit pas), zéro liste
  committée. Ajout d'un projet = `pm-project-new` crée le repo dans le groupe + clone
  en place ; rien à committer dans le client-core.
- **Redmine** = contrôle de cohérence (pm doctor : chaque projet PM ↔ un repo GitLab
  du groupe), **pas** source des droits git.
- Remotes : forme courte par alias SSH (`gitlab:clients/<c>/<p>.git`), convention
  existante.

### 3.6 Résolveur, vue de compatibilité, périmètre partiel

- `pm.config.yml` est déjà la couche d'abstraction prévue pour ça (« déplacer le repo
  projets… sans toucher au code »). Bascule du canonique :
  - `roots.projects_root` → pointe la racine workspaces ;
  - patterns niveau entité : `entity: "{workspaces_root}/{entity}/.mmi-pm"` ;
  - patterns niveau projet : `project: "{workspaces_root}/{entity}/{project}/.mmi-pm"` ;
  - `reverse_link` disparaît (co-location) ; `workspace_link` devient trivial (`..`).
- **Audit nécessaire** : les endroits du code qui présupposent l'arbo
  `clients/<e>/projects/<p>` hors `pm_paths` (iter_projects, find_task, dashboard,
  validator, summarizer, wiki-sync, hooks de tick).
- **Vue de compatibilité transitoire** : `.mmi-pm-core/projects/` gitignoré, peuplé de
  symlinks vers les dossiers clients — maintenue le temps de la migration, supprimée
  ensuite. L'ancien repo `ai-projects` est archivé (lecture seule) après bascule.
- **Marqueur `pm.yml`** dans chaque `.mmi-pm/` (`type: client|project`) : permet au
  pont AGENTS.md et au résolveur de distinguer les deux niveaux sans heuristique.
- **Périmètre partiel (RM1885)** : `iter_*`/`find_task`/liens inter-tickets doivent
  dégrader proprement quand un client/projet référencé n'est pas cloné localement
  (cas hal). Critère d'acceptation du chantier C3.
- **Pont AGENTS.md (RM1892)** : réécrit pour « `.mmi-pm` = dossier » + pointer l'outil
  de gestion (`/zfs/workspaces/.mmi-pm-core/`) ; versionné dans le repo env (§ 3.1).

## 4. Chantiers

### C0 — Hygiène préalable (court, débloque le reste)

| Item | Ticket |
|---|---|
| Réconcilier le push métriques temps/tokens (doublon RM1806/1819) | RM1825 (urgent) |
| Committer les reliquats en attente (RM1910 MD, etc.) | — |
| Amender ADR 0001 + corps RM1887/RM1834 avec les décisions § 2 | RM1887 |
| Passe de validation groupée des ~28 tickets `a_tester_*` | — (lot) |

### C1 — NORMS modulaire, finition

| Item | Ticket |
|---|---|
| Validation demandeur du switchover KERNEL | RM1922 |
| Outillage manquant (doctor complet, --list-next, wrappers git…) | RM1923 |
| Propagation du switchover aux instances fédérées | RM1940 |
| Mesure du contexte réel par rôle (avant/après) + budget de contexte par rôle | **à créer** |

### C2 — Restructuration `/zfs/workspaces` (AVANT l'éclatement)

| Item | Ticket |
|---|---|
| Repo env racine : régularisation du .git, gitignore liste blanche, AGENTS.md versionné, tooling/ | **à créer** |
| Déménagement outil PM → `/zfs/workspaces/.mmi-pm-core/` + submodule | **à créer** (lié RM1940) |
| Inventaire + normalisation `<client>/<projet>` pour tous les clients (remodelage compris, traitement des `git init` sans commit) | **à créer** (chapeau + 1 sous-ticket par client à remodeler) |
| Layout standard bare + dev/ + test/ + .worktrees/ ; miroirs `.products/` ; outillage d'instanciation d'env | **à créer** |
| Outil de statut multi-repos (devient indispensable : ~35 repos de plus) | RM1883 |

### C3 — Éclatement des données PM (co-location)

| Item | Ticket |
|---|---|
| Création groupes GitLab `clients/<c>` + repos core/projets + ACL | RM1887 (impl.) |
| Migration des données `ai-projects` → `.mmi-pm/` par client/projet (avec historique si raisonnable, sinon import à plat + archivage de l'ancien repo) | RM1887 |
| `pm-workspace-sync` (découverte API GitLab + clone/pull sélectif) | **à créer** |
| Bascule résolveur (`pm.config.yml` + audit code) + vue compat + marqueurs `pm.yml` | **à créer** |
| Tolérance périmètre partiel | RM1885 |
| Pont AGENTS.md v2 (`.mmi-pm` dossier) + provisioning | RM1892 |
| Pilote confinement : `hal` limité à 1 repo projet d'1 client | RM1906/1908 |
| Worktrees de session par ticket (par-dessus la nouvelle structure) | RM1834 |
| Symlinks de navigation (si encore utiles après co-location) | RM1769 (réévaluer) |

### C4 — Harmonisation de l'implémentation NORMS

| Item | Ticket |
|---|---|
| Vérifier/harmoniser l'onboarding des 24 projets existants (KERNEL, frontmatters, marqueurs) | **à créer** |
| `pm-project-doctor` : conformité d'un projet (structure, liens, cascade, Redmine) | **à créer** (ou volet de RM1923) |
| Garantie pour les nouveaux projets (pm-project-new/bootstrap alignés sur la cible) | RM1675/1676 (évolution) |

### C5 — Flux de validation & triage

| Item | Ticket |
|---|---|
| CF Redmine « Risque » + « Mode de validation » (auto-validable / demandeur / agent-testeur ; force possible) — design à valider | **à créer** (lié RM1879/1910) |
| Traitement par lots des validations | **à créer** |
| Vue triage ROI dans le cockpit (prochains tickets à plus fort levier) | **à créer** (sous RM1679/1893) |

## 5. Plan de migration (C2→C3)

Principe : **pilote sur 1 client, puis généralisation** ; chaque phase laisse le
système fonctionnel ; sauvegarde complète préalable (faite par Mathieu, 2026-06-12).

- **P0** — Sauvegarde complète + snapshot ZFS. ✔ en cours
- **P1** — Repo env racine (commit initial : .gitignore, AGENTS.md, tooling vide).
  Réversible trivialement.
- **P2** — Pilote normalisation sur 1 client (proposition : `calicote`) : structure
  `<client>/<projet>`, layout bare+dev+test sur 1 projet. Validation humaine.
- **P3** — Généralisation normalisation (1 sous-ticket par client) + `.products/`.
- **P4** — Pilote éclatement PM sur le même client : groupe GitLab, `<client>-core`,
  `.mmi-pm/` committés, vue compat symlinks côté `.mmi-pm-core/projects/`.
- **P5** — Bascule résolveur + généralisation éclatement + archivage `ai-projects`.
- **P6** — Déménagement outil → `.mmi-pm-core/` (submodule), mise à jour AGENTS.md,
  propagation fédération (RM1940), pilote confinement `hal`.
- **P7** — RM1834 (worktrees de session) + nettoyage (suppression vue compat,
  réévaluation RM1769).

## 6. Risques et points ouverts

1. **Multi-sessions pendant la migration** : plusieurs sessions écrivent dans
  `ai-projects` en continu → fenêtre de gel à prévoir par phase (P4/P5), ou migration
  client par client avec redirection au fil de l'eau.
2. **Historique git** : l'extraction par projet avec historique (`git filter-repo`)
  est coûteuse ×24 ; alternative assumée : import à plat + ancien repo archivé en
  lecture seule (l'historique reste consultable). **À trancher.**
3. **Alternates** : un `prune` malheureux sur un miroir `.products/` corrompt les
  emprunteurs → procédure + garde-fou (config) obligatoires dès P3.
4. **Choix de nommage à confirmer** : `.repo.git` (bare projet), `.products/`
  (miroirs), `clients/` (groupe GitLab chapeau), `pm.yml` (marqueur).
5. **Entités hybrides** : clients PM « produit » (prestashop, redmine…) et entité
  `lemathou`/perso — vérifier que le schéma `<client>/<projet>` leur convient tel
  quel (l'inventaire C2 statue).
6. **Cascade dégradée** (hal sans client-core) : quel comportement exact des lectures
  niveau client ? (défauts ? erreur explicite ?) — à spécifier dans RM1885.
7. **Telegram/cockpit/hooks** : les chemins durs éventuels vers `ai/project-management`
  (services systemd sur dev.lxc, bot, hooks) à inventorier avant P6.

## 7. Récapitulatif des tickets à créer (après validation du CDC)

1. Chapeau « Restructuration écosystème workspaces » (porte ce CDC) — relations vers
   RM1887/1885/1834/1883/1892/1906.
2. C1 : budget/mesure de contexte par rôle.
3. C2 : repo env racine ; déménagement `.mmi-pm-core` ; normalisation workspaces
   (chapeau + sous-tickets) ; layout bare/dev/test + `.products/`.
4. C3 : `pm-workspace-sync` ; bascule résolveur + vue compat.
5. C4 : harmonisation 24 projets ; `pm-project-doctor`.
6. C5 : CF Risque/Mode de validation ; validation par lots ; triage ROI cockpit.
