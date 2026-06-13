# Carte des déplacements & créations — restructuration workspaces (C2/C3)

| | |
|---|---|
| **Statut** | DRAFT à valider par Mathieu — **aucun geste tant que cette carte n'est pas validée** |
| **Date** | 2026-06-13 |
| **Base** | `docs/cdc/2026-06-inventaire-workspaces.md` (état des lieux vérifié) |
| **Programme** | RM1942 — chantiers C2 (normalisation dossiers) puis C3 (co-location données) |

## 1. Modèle cible (reformulé d'après tes précisions — à confirmer)

```
/zfs/workspaces/<client>/                  ← dossier CLIENT = repo git  → remote <client>/<client>-core
  .mmi-pm/                                  ← données PM niveau client (client/, memory/, projects_used/) — COMMITÉES
  <projet>/                                 ← dossier PROJET = repo git  → remote <client>/<projet>-core
    .mmi-pm/                                ← données PM niveau projet (project/, tasks/, memory/) — COMMITÉES
    <code…>                                 ← le(s) repo(s) de CODE du projet, gitignoré(s) par le repo -core
```

- Le repo **`-core`** d'un dossier ne tracke (au moins « dans un premier temps ») **que
  son `.mmi-pm/`** ; il gitignore le code. Le **code** garde son/ses propre(s) repo(s)
  (ex. `calyclay/calymix.git`, 118 commits) imbriqué(s) dans le dossier projet.
- `.mmi-pm` cesse d'être un symlink → **dossier réel committé** (la donnée PM voyage
  dans le repo, plus dans le monorepo `ai-projects`).

**⚠ À confirmer avant tout (questions ouvertes, §6) :** le nommage exact des remotes,
le préfixe de groupe GitLab, et 3 divergences de nom workspace↔PM.

## 2. Légende des actions

- **CONV** = conversion sur place : créer le repo `-core`, transformer le symlink
  `.mmi-pm` en dossier réel (déplacer les données depuis `ai-projects`), premier commit.
  **Aucun déplacement de dossier de code.**
- **MOVE** = le dossier de code change d'emplacement (puis CONV).
- **NE PAS TOUCHER** = laissé tel quel (sauf éventuelle CONV du `.mmi-pm`).

## 3. Carte par client — avant → après

### iprospective (les 2 workspaces « à la racine » à ranger)

| Workspace actuel | → Cible | Action | repo code |
|---|---|---|---|
| `/zfs/workspaces/infra` | `/zfs/workspaces/iprospective/infrastructure/infra/` (`.mmi-pm` au niveau `iprospective/infrastructure/`) | **MOVE** | a un remote `gitlab:sysadmin/infrastructure.git` (23 commits) → **préserver le `.git`** |
| `/zfs/workspaces/security` | `/zfs/workspaces/iprospective/security/security/` (`.mmi-pm` au niveau `iprospective/security/`) | **MOVE** | remote `gitlab:…/ai-security.git` (2 commits) → préserver |
| *(pm-ai-agents)* | `ai/project-management` — **cas spécial**, déménage en C2/P6 (`/zfs/workspaces/.mmi-pm-core`), pas ici | — | l'outil lui-même |

→ crée le dossier client `iprospective/` + son repo `iprospective/iprospective-core` (`.mmi-pm` client).

### redmine / roundcube (client = nom du projet)

| Workspace actuel | → Cible | Action |
|---|---|---|
| `/zfs/workspaces/redmine` | `/zfs/workspaces/redmine/redmine/` (contenu dans le sous-dossier ; `.mmi-pm` projet dedans, `.mmi-pm` client au niveau `redmine/`) | **MOVE** (contenu d'un cran) |
| `/zfs/workspaces/roundcube` | `/zfs/workspaces/roundcube/roundcube/` (idem) | **MOVE** |

### calicote (déjà bien rangé — CONV sur place + 1 renommage)

| Workspace actuel | .mmi-pm → PM | Action | repo code |
|---|---|---|---|
| `calicote/dolibarr` | `calicote/dolibarr` | **CONV** | `git init` vide |
| `calicote/prestashop` | `calicote/prestashop` | **CONV** | `git init` vide |
| `calicote/infra` | `calicote/infra` | **CONV** | `git init` vide |
| `calicote/dpsync` | `calicote/**prestasync**` | **CONV + renommer** dossier `dpsync`→`prestasync` (ou aligner le PM) | `git init` vide |

→ crée `calicote/calicote-core` (`.mmi-pm` client).

### calyclay

| Workspace actuel | .mmi-pm → PM | Action | repo code |
|---|---|---|---|
| `calyclay/calymix` | `calyclay/calymix` | **CONV — mais fenêtre calme requise** (projet actif) | `gitlab:calyclay/calymix.git` (118 commits) |
| `calyclay/infra` | `calyclay/infra` | **CONV** | 1 commit local, pas de remote |

→ crée `calyclay/calyclay-core`.

### pisceen (CONV + 1 alignement de nom)

| Workspace actuel | .mmi-pm → PM | Action |
|---|---|---|
| `pisceen/dolibarr` | `pisceen/dolibarr` | **CONV** |
| `pisceen/infra` | `pisceen/infra` | **CONV** |
| `pisceen/presta` | `pisceen/**pisceen-presta**` | **CONV + aligner** (`presta` vs `pisceen-presta`) |

→ crée `pisceen/pisceen-core`.

### lemathou (workspace nommé `perso`)

| Workspace actuel | .mmi-pm → PM | Action |
|---|---|---|
| `perso/maths/maths_v5` (+ autres repos) | `lemathou/maths` | **NE PAS TOUCHER la structure** (client/projet/repos OK) — reste à trancher : `perso` vs `lemathou` (§6) |
| `perso/mathematicians-db` | `lemathou/mathematicians-db` | idem |

### lydiemariller

| Workspace actuel | .mmi-pm → PM | Action |
|---|---|---|
| `lydiemariller/wordpress/dev` | `lydiemariller/lydiemariller-com` | **NE PAS TOUCHER la structure** (client/projet/repo OK) — divergence nom `wordpress` vs `lydiemariller-com` (§6) |

### matnat (structure OK — juste cartographier le PM + nettoyer le vrac)

`matnat/{erp_old, infra, site_sf5, site_sf7}` ont déjà chacun leur `.mmi-pm`. **Ne pas
toucher la structure.** À faire : définir matnat comme client, peupler les 4 projets PM
(0 tâche aujourd'hui), et trier le vrac à la racine `matnat/` (`android-app`, `data/`,
`*.mwb`, `*.txt`, `recup/`…) — hors périmètre restructuration, simple ménage.

### abatik

| Workspace | .mmi-pm → PM | Action |
|---|---|---|
| `abatik/infra` | `abatik/infra` | **CONV** (pas de git aujourd'hui) |

### prestashop (produit)

| Workspace actuel | .mmi-pm → PM | Action |
|---|---|---|
| `prestashop/modules/mmi_productcheck` | `prestashop/mmi_productcheck` | **NE PAS TOUCHER** (le module est déjà un sous-module git sous `modules/`) — divergence de profondeur à statuer (§6) |

### nextcloud (produit)

| Workspace | .mmi-pm → PM | Action |
|---|---|---|
| `nextcloud/nc-clients` | `nextcloud/nc-clients` | **CONV** | `git init` vide |

## 4. Créations nécessaires

### Repos « client-core » à créer (un par client, ⇐ aucun n'existe)

`iprospective-core`, `calicote-core`, `calyclay-core`, `pisceen-core`, `lemathou-core`,
`lydiemariller-core`, `matnat-core`, `abatik-core`, `redmine-core`, `roundcube-core`,
`prestashop-core`, `nextcloud-core`.

### Repos « projet-core » à créer

Un par projet listé en §3 (24 projets). Pour les 7 `git init` vides actuels, le repo
local existe déjà (à brancher sur son remote) ; pour les autres, à initialiser.

### Côté PM (données)

**Aucun projet PM manquant** : les 24 projets existent déjà dans `ai-projects`. Rien à
créer côté PM, **uniquement à migrer** (les `.mmi-pm` deviennent des dossiers réels).
matnat = 4 projets à **peupler** (0 tâche).

## 5. Récap des gestes par niveau de risque

| Risque | Gestes |
|---|---|
| 🟢 Nul | CONV des 7 `git init` vides (calicote ×4, nextcloud, abatik, calyclay/infra) — aucun déplacement, aucun historique en jeu |
| 🟡 Faible | CONV avec alignement de nom (dpsync→prestasync, presta→pisceen-presta) |
| 🟠 Moyen | MOVE avec historique git réel : `infra`, `security` (préserver `.git` + remotes) ; MOVE redmine/roundcube (contenu d'un cran) |
| 🔴 À coordonner | `calyclay/calymix` (actif) ; `ai/project-management` (l'outil, C2/P6) |

## 6. Questions ouvertes — à trancher AVANT tout geste

1. **Nommage des remotes** : confirmes-tu `<client>/<client>-core` et
   `<client>/<projet>-core` ? Et le **groupe GitLab** chapeau : `clients/<client>/…`
   (comme l'ADR) ou directement `<client>/…` ? Les repos `-core` sont-ils **distincts**
   des repos de code (ex. `calyclay/calymix.git` = code, `calyclay/calymix-core.git` =
   données PM) — c'est ma lecture, à valider.
2. **`perso` vs `lemathou`** : le workspace est `perso/`, le client PM est `lemathou`.
   On garde `perso/` et on aligne le slug PM ? on renomme le workspace en `lemathou/` ?
   (idem implicite : `perso` = entité *self* ?)
3. **Divergences de nom workspace↔PM** : `dpsync`/`prestasync`, `presta`/`pisceen-presta`,
   `wordpress`/`lydiemariller-com`, `prestashop/modules/mmi_productcheck` (profondeur).
   Pour chacune : **aligner le dossier sur le PM**, ou **le PM sur le dossier** ?
4. **`.mmi-pm` client niveau redmine/roundcube/prestashop/nextcloud** (entités produit) :
   ont-elles besoin d'un `.mmi-pm` client (donc d'un `*-core`), ou le niveau client est-il
   vide pour ces produits ?
5. **Ordre d'exécution** : on confirme le **pilote** ? (je propose **calicote** : 4 CONV à
   risque nul + 1 renommage, zéro historique en jeu, et tu ne codes pas dessus en ce
   moment — plus serein que calyclay dont calymix est actif).
6. **Repos de code sans remote** (`calyclay/infra`, les `git init` vides) : on leur crée
   un remote de code aussi, ou seul le `-core` (données PM) est versionné pour démarrer ?
