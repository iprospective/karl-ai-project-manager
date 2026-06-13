# Carte des déplacements & créations — restructuration workspaces (C2/C3)

| | |
|---|---|
| **Statut** | **VALIDÉE avec décisions Mathieu 2026-06-13** — pilote = `calicote`. Gestes uniquement après accord pas-à-pas. |
| **Date** | 2026-06-13 |
| **Base** | `docs/cdc/2026-06-inventaire-workspaces.md` (état des lieux vérifié) |
| **Programme** | RM1942 — chantiers C2 (normalisation dossiers) puis C3 (co-location données) |

## 1. Modèle cible (validé)

```
/zfs/workspaces/<client>/                  ← dossier CLIENT = repo git  → remote <client>/<client>-core
  .mmi-pm-client/                           ← données PM niveau client (client/, memory/, projects_used/) — COMMITÉES
  [<groupe>/]<projet>/                       ← dossier PROJET = repo git  → remote <client>/<projet>-core
    .mmi-pm/                                ← données PM niveau projet (project/, tasks/, memory/) — COMMITÉES
    <code…>                                 ← le(s) repo(s) de CODE du projet, gitignoré(s) par le repo -core
```

Décisions actées :
- **Deux marqueurs distincts** (proposition Mathieu, retenue) : `.mmi-pm-client/` au niveau
  client, `.mmi-pm/` au niveau projet. Nommage explicite ⇒ le pont AGENTS.md et le
  résolveur distinguent les deux niveaux **sans marqueur `pm.yml` supplémentaire**.
- **Remotes** : `<client>/<client>-core` et `<client>/<projet>-core`, **distincts des repos
  de code** (ce sont les repos de *structure* des workspaces PM ; le code garde son propre
  repo imbriqué et gitignoré). **Pas de groupe GitLab chapeau `clients/`** — la création
  d'un nouvel env PM sera traitée plus tard.
- **Le repo `-core` ne tracke que son `.mmi-pm[-client]/`** (au moins au début) ; gitignore
  le reste.
- **Groupes de dossiers libres** : un projet peut vivre sous un sous-dossier de
  regroupement (ex. `prestashop/modules/mmi_productcheck`). Le résolveur repère le projet
  par la présence de `.mmi-pm`, **pas** par une profondeur fixe.
- **Noms de dossiers = lisibilité d'abord.** Là où le dossier diverge du slug PM, on garde
  le **nom de dossier** et on réconcilie le PM/les autres outils **plus tard** (ticket).

## 2. Légende des actions

- **CONV** = conversion sur place : créer le repo `-core`, transformer le symlink
  `.mmi-pm` en dossier réel (rapatrier les données depuis `ai-projects`), premier commit.
  **Aucun déplacement de dossier de code.**
- **MOVE** = le dossier de code change d'emplacement (puis CONV).
- **NE PAS TOUCHER** = structure laissée telle quelle (sauf CONV du `.mmi-pm`).

## 3. Carte par client — avant → après

### calicote — ⭐ PILOTE (aucun travail actif dessus)

| Workspace actuel | .mmi-pm → PM | Action |
|---|---|---|
| `calicote/dolibarr` | `calicote/dolibarr` | **CONV** (`git init` vide) |
| `calicote/prestashop` | `calicote/prestashop` | **CONV** (`git init` vide) |
| `calicote/infra` | `calicote/infra` | **CONV** (`git init` vide) |
| `calicote/dpsync` | PM `calicote/prestasync` | **CONV — garder le dossier `dpsync`** ; PM/outils à renommer plus tard (→ ticket T1) |

→ crée `calicote/` `.mmi-pm-client` + remote `calicote/calicote-core`.

### iprospective (workspaces « à la racine » à ranger)

| Workspace actuel | → Cible | Action | repo code |
|---|---|---|---|
| `/zfs/workspaces/infra` | `iprospective/infrastructure/infra/` (`.mmi-pm` au niveau `iprospective/infrastructure/`) | **MOVE** — *actif, fenêtre requise* | remote `gitlab:sysadmin/infrastructure.git` (23 c.) → préserver |
| `/zfs/workspaces/security` | `iprospective/audits/audits/` (`.mmi-pm` au niveau `iprospective/audits/`) | **MOVE** — *actif, fenêtre requise* ; dossier `audits` ↔ PM `security` (→ ticket T1) | remote `gitlab:…/ai-security.git` (2 c.) → préserver |
| *(pm-ai-agents)* | l'outil lui-même → `/zfs/workspaces/.mmi-pm-core` en C2/P6 | — *actif* | — |

→ crée `iprospective/` `.mmi-pm-client` + remote `iprospective/iprospective-core`.

### calyclay — *calymix actif, fenêtre requise*

| Workspace | .mmi-pm → PM | Action | repo code |
|---|---|---|---|
| `calyclay/calymix` | `calyclay/calymix` | **CONV — fenêtre calme** | `gitlab:calyclay/calymix.git` (118 c.) |
| `calyclay/infra` | `calyclay/infra` | **CONV** | 1 commit local, pas de remote |

→ crée `calyclay/calyclay-core`.

### pisceen

| Workspace actuel | .mmi-pm → PM | Action |
|---|---|---|
| `pisceen/dolibarr` | `pisceen/dolibarr` | **CONV** |
| `pisceen/infra` | `pisceen/infra` | **CONV** |
| `pisceen/presta` | `pisceen/pisceen-presta` | **CONV + aligner le dossier** `presta`→`pisceen-presta` |

→ crée `pisceen/pisceen-core`.

### lemathou (workspace nommé `perso` — client canonique = `lemathou`)

| Workspace actuel | .mmi-pm → PM | Action |
|---|---|---|
| `perso/maths/…` | `lemathou/maths` | structure intacte ; client canonique `lemathou` (dossier `perso`→`lemathou`) — *perso/maths **actif**, fenêtre requise* |
| `perso/mathematicians-db` | `lemathou/mathematicians-db` | structure intacte ; idem rattachement `lemathou` |

→ crée `lemathou/lemathou-core`.

### lydiemariller

| Workspace actuel | .mmi-pm → PM | Action |
|---|---|---|
| `lydiemariller/wordpress/dev` | `lydiemariller/lydiemariller-com` | structure intacte ; **aligner le dossier projet** `wordpress`→`lydiemariller-com` |

→ crée `lydiemariller/lydiemariller-core`.

### abatik

| `abatik/infra` | `abatik/infra` | **CONV** (pas de git) → crée `abatik/abatik-core` |
|---|---|---|

### matnat — structure OK, juste cartographier + ménage

`matnat/{erp_old, infra, site_sf5, site_sf7}` ont déjà leur `.mmi-pm`. **Structure intacte.**
À faire : définir matnat comme client (`matnat-core`), **peupler** les 4 projets PM (0 tâche),
trier le vrac racine (`android-app`, `data/`, `*.mwb`, `*.txt`, `recup/`…) — ménage hors
restructuration.

### Entités produit (redmine, roundcube, prestashop, nextcloud)

| Workspace actuel | → Cible | Action |
|---|---|---|
| `/zfs/workspaces/redmine` | `redmine/redmine/` (contenu d'un cran) | **MOVE** |
| `/zfs/workspaces/roundcube` | `roundcube/roundcube/` (contenu d'un cran) | **MOVE** |
| `prestashop/modules/mmi_productcheck` | **inchangé** — `modules/` = sous-dossier de regroupement assumé | NE PAS TOUCHER |
| `nextcloud/nc-clients` | `nextcloud/nc-clients` | **CONV** (`git init` vide) |

→ **`.mmi-pm-client` / `*-core` au niveau produit : différé** (Q4 : « on fait pas si pas
besoin »). À reprendre via ticket si nécessaire (T2).

## 4. Créations

### Repos `-core` à créer (données PM, distincts du code)

- **client-core** (clients réels) : `calicote-core`, `iprospective-core`, `calyclay-core`,
  `pisceen-core`, `lemathou-core`, `lydiemariller-core`, `matnat-core`, `abatik-core`.
- **client-core produits** (redmine, roundcube, prestashop, nextcloud) : **différé** (T2).
- **projet-core** : un par projet (les 7 `git init` vides ont déjà le repo local, à brancher
  sur leur remote ; les autres à initialiser au passage).

### Côté PM (données)

Aucun projet PM manquant (24 existent). **Migration seule** : `.mmi-pm` symlink → dossier
réel. matnat = 4 projets à peupler.

## 5. Risque & coordination

| Risque | Gestes |
|---|---|
| 🟢 Nul | CONV des `git init` vides : **calicote ×4** (pilote), nextcloud, abatik, calyclay/infra |
| 🟡 Faible | CONV + alignement de dossier : pisceen (`presta`→`pisceen-presta`), lydiemariller (`wordpress`→`lydiemariller-com`) |
| 🟠 Moyen | MOVE avec historique git : redmine, roundcube (contenu d'un cran) |
| 🔴 Fenêtre requise (**projets actifs**) | `security`→`iprospective/audits`, `infra`→`iprospective/infrastructure`, `calyclay/calymix`, `ai/project-management` (l'outil), `perso/maths` |

**Projets actifs à ne migrer que sur fenêtre calme annoncée** : security, calyclay/calymix,
infra, ai/project-management, perso/maths.

## 6. Décisions validées (2026-06-13)

1. Remotes `<client>/<client>-core` + `<client>/<projet>-core`, distincts du code, **sans**
   groupe chapeau `clients/`.
2. Marqueurs `.mmi-pm-client` (client) / `.mmi-pm` (projet).
3. Noms de dossier conservés pour lisibilité ; PM/outils réconciliés plus tard où ça diverge.
4. Client PM `lemathou` (pas `perso`).
5. `modules/mmi_productcheck` conservé (regroupement par sous-dossier assumé).
6. `.mmi-pm-client` produits : différé tant qu'inutile.
7. Pilote = **calicote**.

## 7. Tickets à créer (réconciliations différées)

- **T1 — Réconcilier les noms divergents dossier↔PM/outils** : `dpsync`↔`prestasync`,
  `audits`↔`security` (renommer le PM + autres outils sur le nom de dossier lisible).
- **T2 — `.mmi-pm-client`/`-core` pour les entités produit** : à évaluer si le besoin
  apparaît (redmine, roundcube, prestashop, nextcloud).
- **T3 — Remotes de code** pour les workspaces qui n'en ont pas (`calyclay/infra`, les
  `git init` vides) : créés seulement si nécessaires à la migration, sinon notés ici.
- **matnat** : peupler les 4 projets PM + ménage du vrac racine.

## 8. Pilote — RÉSULTAT (2026-06-13) ✅

Premier geste exécuté sur **calicote** : `calicote/calicote-core` (`.mmi-pm-client`) +
`calicote/dolibarr-core` (`.mmi-pm` ex-symlink → dossier réel). Créés sur GitLab (groupe
top-level `calicote/` après promotion `sfy/calicote`→`calicote`), pushés (SHA local=remote).
`ai-projects` conservé en parallèle (« on garde les deux »). Résolveur + `pm-doctor` verts.

**Procédure CONV validée de bout en bout** (à rejouer pour chaque projet) :
1. créer le repo `<client>/<projet>-core` (et `<client>-core` une fois par client) ;
2. `.mmi-pm-client/` (client) / `.mmi-pm/` (projet) = **copie** des données depuis
   `ai-projects` (l'original reste) ; pour un projet, le symlink `.mmi-pm` est remplacé
   par le dossier (`rm` du symlink seul → cible ai-projects intacte) ;
3. `.gitignore` whitelist (`/*` + `!/.gitignore` + `!/.mmi-pm[-client]/`) → ne tracke que
   le PM, ignore le code ; vérifier qu'aucun code n'est stagé ;
4. premier commit + push.

**Apprentissage (résolu RM1949)** : la détection « projet courant » lisait le **symlink**
`.mmi-pm` → cassée sur un dossier. Corrigé par une détection **unique overview-based**
(`PMConfig.detect_project_from_cwd` lit `.mmi-pm/project/overview.md` → `client`+`slug`,
marche pour symlink ET dossier ; un seul mécanisme, pas de marqueur). Le `.mmi-pm` co-localisé
est donc **auto-suffisant** pour la détection.

**Suite immédiate** : 3 autres projets calicote — `prestashop`, `infra`, `dpsync` (même
CONV, risque nul ; `prestashop` a ses repos code `dev/`/`test/` gitignorés).
