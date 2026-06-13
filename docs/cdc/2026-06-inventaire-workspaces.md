# Inventaire /zfs/workspaces — état des lieux avant restructuration (C2)

| | |
|---|---|
| **Statut** | Constat vérifié (lecture seule) — base de décision pour RM1946 (C2 du programme RM1942) |
| **Date** | 2026-06-13 |
| **Méthode** | Balayage agent + **vérification manuelle des points critiques** (l'agent avait produit 2 affirmations fausses, corrigées ci-dessous) |

## Corrections d'un premier balayage erroné (pour mémoire)

- ❌ « `ai/project-management` est sur `master`, sans remote, isolé » → **FAUX** : branche
  `dev`, remote `gitlab:…/ai-project-management.git`, à jour. (C'est le repo de travail.)
- ❌ « `/zfs/workspaces/ai/` est un repo git avec 42 fichiers dirty » → **FAUX** :
  `/zfs/workspaces/ai/` n'est **pas** un repo git du tout.
- ❌ « aucun workspace projet n'a de git local » → **FAUX** : plusieurs en ont un
  (voir tableau).

## Vue d'ensemble

47 entrées à la racine. Pertinents pour la restructuration PM : **25 symlinks `.mmi-pm`**
(tous valides), répartis en workspaces clients + entités produit. Aucun workspace n'est
encore à la structure cible pure `<client>/<projet>` co-localisée.

## Tableau d'état & action proposée (trié par risque croissant)

### G0 — Ne touche à rien (sain ou actif)

| Élément | État | Action |
|---|---|---|
| `/zfs/workspaces/.git` | git init, branche master, **0 commit, 0 fichier tracké** | C'est le **futur repo « env » racine** (RM1944). Vide ⇒ rien à perdre. À peupler proprement en C2, pas avant. |
| `calyclay/calymix` | repo propre, remote `gitlab:calyclay/calymix.git`, **118 commits**, déjà `<client>/<projet>` | **NE PAS TOUCHER** — projet **actif** (Mathieu code dessus en //). |

### G1 — `git init` sans commit (« préparer le terrain ») — à régulariser

Repos initialisés mais **vides** (0 commit, pas de remote) : décider par projet → soit
premier commit + remote GitLab, soit retrait du `.git` vide.

| Workspace | Remote | Commits |
|---|---|---|
| `calicote/dolibarr` | aucun | 0 |
| `calicote/prestashop` | aucun | 0 |
| `calicote/infra` | aucun | 0 |
| `calicote/dpsync` | aucun | 0 |
| `nextcloud/nc-clients` | aucun | 0 |
| `perso/mathematicians-db` | aucun | 0 |
| `calyclay/infra` | aucun | **1** (1 commit local, pas de remote) |

### G2 — Workspaces « top-level » à promouvoir en `<client>/<projet>`

Workspaces posés à la racine au lieu d'être sous leur client. **Attention** : `infra` et
`security` ont un **historique git réel avec remote** → déplacement à faire en préservant
le `.git` (pas un simple `mv` à l'aveugle).

| Racine actuelle | Cible PM | Git | Remote |
|---|---|---|---|
| `/zfs/workspaces/infra` | `iprospective/infrastructure` | 23 commits | `gitlab:sysadmin/infrastructure.git` |
| `/zfs/workspaces/security` | `iprospective/security` | 2 commits | `gitlab:…/ai-security.git` |
| `/zfs/workspaces/redmine` | `redmine/redmine` | pas de git | — |
| `/zfs/workspaces/roundcube` | `roundcube/roundcube` | pas de git | — |

### G3 — Workspaces imbriqués à aplatir

| Actuel | Cible |
|---|---|
| `perso/maths/…` | `lemathou/maths` |
| `perso/mathematicians-db` | `lemathou/mathematicians-db` |
| `lydiemariller/wordpress/dev` | `lydiemariller/lydiemariller-com` |

### G4 — À trier (probablement obsolète)

| Élément | État |
|---|---|
| `matnat` (workspace) | Dépotoir pré-PM (`android-app`, `data`, `*.mwb`, `*.txt`, `recup/`…) ; côté PM : 4 projets (`erp_old`, `infra`, `site_sf5`, `site_sf7`) **avec 0 tâche**. Statuer : encore actif ? archiver ? |

## Clone fédéré (B)

`/zfs/workspaces/iprospective/ai-project-management` : branche `dev`, **arbre propre**
(0 dirty), mais ses refs sont **en retard** sur le vrai remote (dernier commit local
`f6461e3` = RM1922, alors que le remote est à `aebe9b5` = RM1943). → un simple
`git fetch && git pull` (fast-forward, sans risque) le remet à niveau. À faire **avant**
toute propagation (ex-RM1940, replié dans C2).

## Chemins durs vers `ai/project-management` (n'impactent que le déménagement du repo OUTIL, tardif)

Le chemin absolu est codé en dur dans (tous **internes** au repo, donc voyagent avec lui,
mais leur **contenu** devra être réécrit au moment du move) :
- `.claude/settings.json` + `.claude/settings.local.json` (allowlist scripts)
- `deploy/karl-agent/install.sh` (variable REPO)
- `tools/synchro/lib/helpers.sh`

→ À traiter seulement en **C2/P6** (déménagement de l'outil), pas avant ; via `sed` au
moment du move + redémarrage des services. Sans objet tant qu'on ne déplace pas l'outil.

## Ce que cet inventaire confirme

1. **Rien d'irréversible n'a été fait** ; aucun `.mmi-pm` n'est encore converti, aucun
   dossier déplacé.
2. Le seul « git init sans commit » inquiétant en apparence (`/zfs/workspaces/.git`) est
   en réalité **vide et attendu** — c'est le futur repo env.
3. Les déplacements **délicats** (historique git réel) se limitent à `infra` et
   `security` — tout le reste est soit vide, soit sans git.
4. Le pilote prévu **calyclay** mérite une nuance : `calymix` est **activement codé**
   → piloter plutôt sur un projet calme du même client, ou attendre une fenêtre où
   Mathieu n'y travaille pas.
