# CDC — Commande `mmi-pm` (point d'entrée sudo unique de provisioning PM)

> Ticket : **RM1680** (re-scopé, en étude). Relié : RM1948 (import/découverte),
> RM1885 (env partiel/index), RM1886 (déploiement par script), RM1993/1946/1947
> (structure dossiers), RM1945 (déménagement outil = substrat `.mmi-pm-core`).
>
> **Statut : BROUILLON — co-rédigé Mathieu + agent.** Les sections marquées
> `❓DÉCISION` sont à trancher ensemble avant rédaction définitive.

## 1. Objectif & périmètre

`mmi-pm` = **point d'entrée CLI unique** de l'écosystème PM, et **seule porte sudo**
des opérations privilégiées (création de dossiers à la racine workspace verrouillée,
clone vers emplacement canonique, chown, MAJ de l'outil). Centralise create / import /
update des clients, projets et de l'outil lui-même, et **maintient l'index** du
résolveur.

- **Hors périmètre v1** : (à préciser).
- **Périmètre v1** : (à préciser — cf. §12 phasage).

## 2. Modèle de sécurité

> **⚠ RÉVISION 2026-06-15 (à intégrer) :** Mathieu préfère finalement un **user dédié
> `mathieu-pm`** (PAS `root`) pour la propriété ET le sudo de l'outil. → remplacer partout
> `root:root` par `mathieu-pm:mathieu-pm`, et `sudo` (root) par `sudo -u mathieu-pm` (D3/§13a +
> dispatcher). `KARL_USER` (runtime agent = `mathieu`) reste distinct (lecture seule). Le user
> sudo dédié doit être un **paramètre de config** (ex. `KARL_SUDO_USER` dans `.env`, à côté de
> `KARL_USER`), pas en dur → fédération.

- `.mmi-pm-core` = `root:root` *(→ `mathieu-pm`, cf. révision)* (outil de prod non agent-writable — RM1945).
- `mmi-pm` **re-exec en sudo uniquement** les sous-commandes privilégiées ; les
  lectures / task-ops tournent en tant que `KARL_USER` (déclaré dans `.env`).
- Clone effectué **en tant que `KARL_USER` puis chown** (jamais clone-as-root : hooks git).
- **§2a Frontière sudo — ✅ DÉCIDÉ (D3, 2026-06-15) : re-exec sélectif.** `mmi-pm` classe
  chaque sous-commande (privilégiée vs non). Si privilégiée et pas root → il **se re-exec
  via `sudo`** (règle **sudoers** autorisant `KARL_USER` à lancer le binaire). Les
  lectures / task-ops tournent **directement en agent**. Un seul point d'entrée, sudo
  seulement quand nécessaire.

## 3. Architecture du dispatcher

- Binaire `.mmi-pm-core/bin/mmi-pm`, exposé sur le `PATH` (symlink `/usr/local/bin/mmi-pm`).
- **§3a Implémentation — ✅ DÉCIDÉ (D4, 2026-06-15) : dispatcher mince.** `mmi-pm` **route**
  les sous-commandes vers les **`pm-*.py` existants** (sous-process), gère le privilège/sudo
  (§2a) et le maintien de l'index (§5). Réutilise tout l'existant (auto-commit RM1834-A
  inclus), risque minimal, livrable rapide. Refactor en lib commune = évolution ultérieure
  possible, hors v1.
- Relation avec les skills `mmi-pm-*` (Claude) : les skills restent des wrappers
  contextuels ; `mmi-pm` est le pendant shell/sudo, idéalement appuyé sur la même logique.

## 4. Identifiabilité d'un repo PM  ✅ DÉCIDÉ (D1 — **FINAL 2026-06-15 : `meta.yml`**)

**Séparation donnée / prose** (décision Mathieu après réflexion ; on abandonne le frontmatter-dans-MD) :
- **`meta.yml`** = manifeste **machine** (= l'actuel frontmatter d'`overview.md` : `slug`, `name`,
  `client`, `status`, `gitlab`, `redmine`, `bootstrap`, `defaults`, `aspects`…). Format **YAML**
  (cohérent avec tout le système ; TOML écarté : données imbriquées + listes-de-maps, et écosystème
  déjà 100 % YAML).
- **`overview.md`** = **prose pure** (description détaillée), **plus de frontmatter**.
- Emplacement : `.mmi-pm/meta.yml` (projet) / `.mmi-pm-client/meta.yml` (client) — *à confirmer*.

**Marqueur D1** = présence de `meta.yml`. Le **scan** (§8) teste `.mmi-pm[-client]/meta.yml` (API
d'arbre, sans clone) et le lit pour le catalogue.

Bénéfices : **un seul parser** (`yaml.safe_load`) au lieu de ~40 lectures de frontmatter dispersées
(dette remboursée) ; prose propre ; **sync Redmine simplifiée**.

⚠ **Implique un refactor** (~40 lecteurs de frontmatter + migration des données) → **chantier dédié
(ticket)**. `mmi-pm index rebuild` lira `meta.yml` (aujourd'hui il lit `overview.md` — bascule
triviale une fois `meta.yml` en place).

**Noms de dossiers — gardés (décision 2026-06-15)** : `.mmi-pm` (projet) / `.mmi-pm-client` (client).
`meta.yml.type` porte désormais le niveau, mais la distinction de nom **aide la lisibilité** ;
renommer serait load-bearing (onboarding `/zfs/workspaces/AGENTS.md`, résolveur, symlinks d'index) →
non justifié. Changeable plus tard sans drame si besoin.

## 5. Index résolveur

- Maintenu par `mmi-pm` à chaque create / import / update : symlinks
  `clients/<c>/projects/<p>` → emplacement canonique.
- Emplacement : `.mmi-pm-core/projects/` (= `PROJECTS_PATH`, gitignoré, survit à
  `core update`). **Forme identique à l'actuel** → quasi zéro changement `pm_paths`.
- Niveau client : `.mmi-pm-client` (idem). (détailler)

## 6. Emplacements canoniques

- Client : `/zfs/workspaces/<client>/` ; projet : `/zfs/workspaces/<client>/<projet>/`.
- Norme `<projet>/dev` (code dans `dev/`, `.mmi-pm` à la racine projet). (détailler)

## 7. Sous-commandes (matrice — à affiner)

| Commande | Rôle | Params |
|---|---|---|
| `mmi-pm client new <slug>` | crée un client | … |
| `mmi-pm client import <git-url> [dest]` | clone un `<client>-core` | … |
| `mmi-pm project new …` | crée un projet | … |
| `mmi-pm project import <git-url> <client> [dest]` | importe un projet révisionné | … |
| `mmi-pm core update` | pull/màj de l'outil (sudo) | — |
| `mmi-pm source add\|list\|scan …` | dépôts PM (§8) | … |
| `mmi-pm list\|doctor …` | inventaire / diagnostic | … |

## 8. Dépôts PM — modèle « APT »

Déclarer **plusieurs sources git** (gitlab.iprospective.fr, github, …) comme dépôts PM.
PM les scanne, **maintient un catalogue** des clients/projets disponibles, facilite
l'import local.

**§8a Mapping — ✅ DÉCIDÉ (D2, 2026-06-15) : hybride.** Découverte par **groupe/namespace**
(GitLab group / GitHub org) pour l'efficacité du scan, mais le **frontmatter d'`overview.md`
fait foi** (slug, type, et pour un projet `client`). S'appuie sur la structure existante
(1 groupe ≈ 1 client, `<client>-core` + `<projet>-core` dedans) tout en restant robuste
multi-source ; le rattachement projet→client vient du manifeste, pas (seulement) du groupe.

**§8b — ❓DÉCISION** : mécanisme de scan (API GitLab/GitHub vs `git ls-remote` vs clone
shallow — reco : API d'arbre pour tester `.mmi-pm[-client]/…/overview.md` sans clone) ; stockage
& format du catalogue (emplacement, rafraîchissement).

## 9. Remote git optionnel

Chaque client/projet **peut** (recommandé) être associé à un remote. Sinon → **init repo
local** + **auto-commit PM** (RM1834-A). (détailler le choix par défaut)

## 10. Migration de l'existant

**Quasi nulle** : `mmi-pm index rebuild` régénère l'index depuis les `overview.md` co-localisés
(slugs/clients corrects, déjà présents). Vérifié **diff-vide 25/25**. Seul ajout futur : le champ
`path` au frontmatter `overview` des projets hors-norme (worm) pour fiabiliser l'**import** (Lot 3) ;
la *découverte* locale par `find` les gère déjà sans ce champ.

## 11. Liens & compatibilité

Absorbe l'ancien périmètre « wrapper `pm` » de RM1680. Voir relations en tête.

## 12. Phasage & critères d'acceptation

- **Lot 1 — Socle dispatcher ✅ VALIDÉ (2026-06-15)** : `bin/mmi-pm` + classification
  priv/non-priv + re-exec sudo + règle sudoers + `mmi-pm core update` + helper de maintien
  d'index. Minimum utilisable, **débloque la fin de la bascule `.mmi-pm-core`**. Spec → §13.
- **Lot 2 — Provisioning local** *(à revoir)* : `client new`/`project new`/`client import`/
  `project import`.
- **Lot 3 — Dépôts PM** *(à revoir)* : `source add/list/scan` + catalogue.
- Transverse : ~~schéma `pm.yml`~~ → **abandonné** (manifeste = `overview.md`). Reste : ajouter
  le champ `path` (emplacement canonique) au frontmatter `overview` pour catalogue/import (Lot 3).
- Critères d'acceptation : (à compléter par lot).

## 13. Lot 1 — spécification détaillée

**Grammaire** : `mmi-pm <nom> <verbe> [args]` (cf. exemples Mathieu : `client new`,
`project import`, `core update`). Nom = `client|project|core|source|index`.

**Classification des sous-commandes (D3)** :
- *Privilégiées* (re-exec sudo) : tout ce qui crée/déplace des dossiers à la racine
  workspace verrouillée, chown, ou modifie `.mmi-pm-core` (ex. `core update`, `*/import`,
  `*/new`, `index rebuild`).
- *Non privilégiées* (agent direct) : lectures / diagnostic (`list`, `doctor`, `index show`).

**Commandes du Lot 1** :
- `mmi-pm core update` *(priv)* — met à jour l'outil déployé : en root, `git -C .mmi-pm-core`
  fetch + checkout de la branche épinglée (`main`), `submodule update`, **re-verrouille**
  l'ownership (root:root), met à jour le pointeur de submodule du repo env. ❓ détail :
  faut-il committer le nouveau pin du repo env automatiquement ?
- `mmi-pm index add|remove <client>[/<projet>]` *(priv)* — crée/retire le symlink
  `projects/clients/<c>/projects/<p>` → emplacement canonique. Brique réutilisée par le Lot 2.
- `mmi-pm index rebuild` *(priv)* — reconstruit l'index depuis les `.mmi-pm[-client]/` trouvés
  aux emplacements canoniques (utile migration §10).
- `mmi-pm list` / `mmi-pm doctor` *(non priv)* — inventaire / diagnostic (réutilise `pm-doctor`).

**Règle sudoers — ✅ DÉCIDÉ (§13a, 2026-06-15) : mot de passe requis.** Pas de NOPASSWD :
chaque opération privilégiée demande le mot de passe sudo (barrière humaine, surface
d'attaque réduite). `mmi-pm` doit quand même valider strictement ses args. Friction
assumée (les ops privilégiées sont peu fréquentes : create/import/update).

**Critères d'acceptation Lot 1** :
- [x] dispatcher : grammaire `<nom> <verbe>`, `--help`, `bash -n` OK.
- [x] sous-commande non-priv (list/doctor/dry-run) lancée par l'agent **ne déclenche pas sudo**.
- [x] sous-commande priv en agent → **re-exec sudo** (mot de passe) ; `--dry-run` prévisualise sans sudo.
- [x] `index rebuild` = **diff vide** vs index actuel — via `overview.md` (vérifié **25/25**,
  inclut `worm`) ; un `.mmi-pm` symlink (ancienne instance) n'est pas traversé par `find` → exclu.
- [ ] `mmi-pm core update` met à jour + re-verrouille — *codé + dry-run OK ; test réel après
  provisioning de `.mmi-pm-core` (bascule Phase 2 ; chown → `KARL_SUDO_USER`, cf. révision §2)*.
