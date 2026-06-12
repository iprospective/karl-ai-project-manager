# ADR 0001 — Découpage des données PM en repos par client (orchestrateur à périmètre restreint)

- **Statut** : **AMENDÉ le 2026-06-12** (cf. § Amendement ci-dessous) — granularité et montage
  supersédés par le CDC `docs/cdc/2026-06-restructuration-workspaces-pm.md`. Driver tranché le
  2026-06-09 — cette étude est la **facette données/GitLab** du chapeau **RM1906** (orchestrateur
  client-facing multi-tenant confiné).
- **Date** : 2026-06-08 (driver réel ajouté 2026-06-09 ; amendement 2026-06-12)
- **Tickets** : **RM1906** (chapeau multi-tenant) — RM1887 (cette étude = facette données) — RM1907 (Redmine) / RM1908 (SSH+isolation) / RM1909 (provisioning+pilotage) facettes sœurs — RM1885 (périmètre restreint) — RM1769 (symlinks niveau client) — RM1872 (friction pointeur submodule) — fédération (RM1802/RM1859)

## ⚠ Amendement 2026-06-12 — granularité et montage supersédés

Décisions de Mathieu (session 2026-06-09 « B : repos par projet », confirmées et complétées
le 2026-06-12, consignées dans le **CDC `docs/cdc/2026-06-restructuration-workspaces-pm.md`**,
qui devient le document de référence) :

1. **Granularité : repo par PROJET** (l'option E ci-dessous, rejetée par l'étude, est
   **retenue**) + un repo « **cœur client** » (`<client>-core`) par client. Le grain des
   **droits** reste double : groupe GitLab `clients/<C>` (client entier) **ou** repo projet
   individuel (instance limitée à un projet, ex. `hal`).
2. **Montage : co-location** (« Modèle 2 ») — la donnée PM d'un projet vit dans
   `<workspace projet>/.mmi-pm/` (dossier réel **committé** dans le repo du workspace
   projet) ; celle du client dans `<workspace client>/.mmi-pm/` (repo `<client>-core`).
   Côté outil PM, `projects/` devient une **vue gitignorée** (symlinks), et le canonique
   du résolveur bascule vers les workspaces.

Les objections de l'étude contre l'option E sont résolues par le nouveau design :
- *« cascade client→projet éclatée »* → relogée dans le repo cœur client ;
- *« 22+ repos, lourd »* → gérés par **découverte dynamique via l'API GitLab**
  (`pm-workspace-sync` : on clone ce que le token voit, aucune liste committée) ;
- le rejet des **submodules** (option C) est lui **confirmé et étendu** : pas de submodule
  non plus entre client-core et projets.

Le reste de l'étude (faits mesurés, analyse des options, effets de bord) demeure valide
comme matériau historique ; les sections « Recommandation » et « Plan de migration »
ci-dessous sont **remplacées** par les chantiers C2/C3 et phases P0–P7 du CDC.

## Driver réel (tranché 2026-06-09)

La question pivot « besoin de droits par client ? » est tranchée, mais **pas** par la
ségrégation interne (déjà couverte par les users/groupes GitLab). Le vrai moteur : **on met
l'orchestrateur à disposition des clients, et le client pilote directement** → le tenant
`karl-<client>` est **quasi-untrusted** et doit être **confiné sur 4 plans** (Redmine, GitLab,
SSH, secrets) + **isolé** dans un substrat dédié. C'est ce qui force réellement le repo-par-client :
un compte de service `karl-<client>` doit porter un **credential GitLab incapable de lire la donnée
des autres clients** — impossible avec un monorepo.

→ **Option D retenue** (repo PM par client), comme **pré-requis données** du confinement GitLab.
Le design d'ensemble vit dans **RM1906** ; cet ADR ne couvre que la facette données/GitLab.
Sparse-checkout (option B) reste le fallback si le client-facing n'est finalement pas déployé.

## Contexte

Aujourd'hui toutes les données PM (cahiers des charges, tâches, mémoire de tous les
clients/projets) vivent dans **un seul repo `ai-projects`**
(`gitlab:iprospective/ai-artificial-intelligence/ai-projects.git`), monté à
`{projects_root}` (= `project-management/projects/`, gitignored dans le repo système).

On veut deux choses :

1. **(RM1885)** Qu'un environnement orchestrateur (ou une instance fédérée : karl, hal, …)
   puisse ne porter que **quelques clients/projets**, pas tout.
2. **(objectif de cette étude)** Pouvoir poser des **droits d'accès au niveau repo GitLab**,
   par client — piste proposée : *« un nouveau repo par client, fusionné dans le workspace
   client via un lien symbolique pour ne rien casser »*.

## Faits établis (mesurés le 2026-06-08)

| Fait | Valeur | Conséquence |
|---|---|---|
| `ai-projects` est déjà un repo distinct | oui, gitignored dans `project-management` | « migrer pm-clients » = **restructurer ce repo**, pas en extraire un |
| Taille | **1,7 M** worktree, 2,3 M `.git`, 219 tâches, 11 entités, 22 projets | la **lourdeur n'est pas un problème de taille/perf** — le seul moteur réel est *droits + périmètre* |
| `iter_entities()`/`iter_projects()` | `if p.is_dir() and not p.is_symlink()` | **skippent les symlinks** → la piste « montage par symlink » casse l'itération sans patch |
| skip symlink niveau **entité** | purement **défensif** (aucun symlink d'entité légitime aujourd'hui) | relaxable en ~3 lignes |
| `projects_used/` (cross-client) | 9 dossiers, **0 symlink actif** | risque migration cross-client **faible** aujourd'hui |
| Submodules | RM1872 montre que le **bump de pointeur** est déjà une friction sur le code | argument contre les submodules pour de la donnée **faiblement couplée** |
| Fédération (mémoire 2026-06-07) | « clones git indépendants par machine », « seul pusher de SON instance », propriété par ticket | un découpage par client **réduit** la contention et **colle** à ce cap |

## Constat pivot : deux besoins, deux solutions les moins chères différentes

- **Si le seul besoin est le périmètre restreint (RM1885)** → `git sparse-checkout` sur le
  monorepo existant suffit : on ne checkout que `clients/<C>/…`, les dossiers absents ne sont
  pas dans le worktree, donc `iter_entities()` ne voit que ce qui est présent. **Zéro
  restructuration, zéro changement de code.** Mais **ne donne aucun droit GitLab par client**
  (sparse-checkout est une feature de worktree, pas de contrôle d'accès — tout le monde ayant
  accès au repo voit tout l'historique).
- **Si on veut des droits GitLab par client** → il faut **des repos séparés**. C'est la seule
  façon d'avoir un contrôle d'accès par client sur GitLab (les ACL GitLab sont au niveau repo,
  pas au niveau chemin).

➡️ **Question qui conditionne tout (à trancher en validation)** : a-t-on un **vrai besoin de
cloisonnement d'accès par client** (collaborateurs externes, repos client-facing,
confidentialité inter-clients) — ou seulement un orchestrateur plus léger ?

## Options évaluées

| # | Option | Périmètre restreint (RM1885) | Droits GitLab/client | Casse qqch ? | Coût récurrent |
|---|---|:--:|:--:|---|---|
| A | Statu quo (monorepo) | ✗ (sauf sparse) | ✗ | non | nul |
| B | **Sparse-checkout** sur monorepo | ✓ | ✗ | non (0 code) | nul |
| C | Repo/client via **submodules** (superprojet ai-projects) | ✓ | ✓ | quasi non | **élevé** : bump pointeur (cf RM1872 ×N), HEAD détachée, versionnage croisé inutile |
| D | **Repo/client indépendant monté en place** (piste proposée) | ✓ | ✓ | petit patch `iter_entities` | **faible** : pas de superprojet à versionner |
| E | Repo **par projet** | ✓ (fin) | ✓ (fin) | cascade client→projet **éclatée** | 22+ repos, lourd |
| F | **Manifest** (google repo / west) | ✓ | ✓ | outil en plus | overkill pour ~11 repos |

### Pourquoi D > C pour de la donnée PM

Les submodules brillent quand il faut **épingler des versions exactes de façon atomique** à
travers un ensemble (dépendances de code). La donnée PM est **faiblement couplée** : chaque
client est indépendant, « HEAD = dernière version » suffit, on n'a **jamais** besoin d'une
cohérence atomique inter-clients. On paierait donc tout le coût submodule (cérémonie de bump
de pointeur déjà identifiée en friction sur RM1872, HEAD détachée à expliquer aux agents)
**sans bénéfice**. L'instinct de la piste proposée (repos indépendants montés en place) est
**fondé** pour ce cas d'usage.

### Le crux symlink (et sa résolution)

`iter_entities()`/`iter_projects()` font `not p.is_symlink()`. Le skip au **niveau projet**
protège les vues `projects_used/` (cross-client) ; le skip au **niveau entité** est purement
défensif (aucun symlink d'entité aujourd'hui). Deux façons de monter un repo/client sans casser :

- **(i) Dossier réel** : le clone vit directement à `clients/<C>` (ou bind-mount) → **aucun
  changement de code**. La « fusion dans le workspace » se fait alors par les **symlinks
  bidirectionnels niveau client de RM1769** (`.mmi-pm-client` ↔ `workspace`), qui sont de la
  **navigation**, pas le mécanisme de montage.
- **(ii) Symlink** : relaxer `iter_entities` pour **suivre les symlinks de dossier** au niveau
  entité (résoudre + `is_dir()`), en continuant d'ignorer les symlinks sous `projects_used/`.
  ~3 lignes + tests.

On garde ces deux préoccupations **séparées** : *mécanisme de montage des données* d'un côté,
*confort de navigation (RM1769)* de l'autre.

## Recommandation

1. **Trancher d'abord le besoin de droits** (question pivot ci-dessus).
   - Besoin de droits par client **non confirmé** → **Option B (sparse-checkout)** : répond à
     RM1885 immédiatement, sans rien restructurer. Stop.
   - Besoin de droits par client **confirmé** → **Option D**, granularité **par client**.
2. **Granularité = par client**, pas par projet : le client est la frontière d'accès naturelle,
   la cascade `client → projet → tâche` reste **locale** dans un seul repo, et 11 repos restent
   gérables (22+ ne le sont pas).
3. **Modèle mixte autorisé** (le mécanisme de montage est uniforme) : clients confidentiels →
   repo dédié `iprospective/pm-clients/<C>` ; entités non sensibles (`product`/`self` :
   redmine, prestashop, roundcube, nextcloud, iprospective, lemathou) → peuvent **rester
   groupées** dans un repo « cœur » `ai-projects-core` tant qu'aucun cloisonnement n'est requis.
4. **Montage** : privilégier le **dossier réel** (option i, zéro code) si la topologie le permet ;
   sinon appliquer le petit patch `iter_entities` (option ii). Le confort « vue depuis le
   workspace client » est fourni par **RM1769**, pas par le montage.

## Effets de bord à traiter (checklist d'implémentation)

- `pm.config.yml` / `pm_paths.py` : `entities_dir` inchangé ; si montage symlink → patch
  `iter_entities`/`iter_projects` (suivre symlinks de dossier au niveau entité, garder le skip
  sous `projects_used/`).
- `find_task`/dashboard/validator/summarizer/status-update : sur périmètre restreint, un ticket
  d'un client non monté → `find_task` renvoie déjà `None` (comportement déjà sûr) ; vérifier la
  dégradation gracieuse partout.
- `.mmi-pm` (reverse_link) des workspaces de code → pointent vers `clients/<C>/projects/<P>` :
  **chemin préservé** par le découpage, rien à changer.
- Cross-client (`used_by_clients`/`projects_used`) : `pm sync-views` (à écrire) doit générer des
  symlinks **absolus** et **skipper les fournisseurs non montés** (dangling-safe). Faible enjeu
  aujourd'hui (0 symlink actif).
- commit+push (NORMS) : une session touchant le client X push **uniquement** le repo X →
  **réduit** la contention ; cohérent avec « seul pusher de SON instance » (fédération).
- GitLab API : gotcha `%2F` (NORMS) → créer les repos via **ID numérique**, pas chemin encodé.
- `pm doctor` : ajouter un check « client référencé mais non monté dans ce périmètre ».

## Plan de migration (incrémental, faible risque vu la taille)

- **P0** — valider cette étude (besoin de droits ? granularité ?).
- **P1** — patch d'activation `iter_entities` (suivre symlinks de dossier) **+ tests** ;
  non-bloquant, le monorepo continue de marcher.
- **P2** — **pilote 1 client** (ex. `calicote` ou `pisceen`) : créer le repo GitLab,
  préserver l'historique (`git filter-repo`/`subtree split` — rapide vu 1,7 M, ou init neuf si
  l'historique n'est pas précieux), poser les droits, monter en place, **re-jouer dashboard /
  validator / find_task / status-update / link** → tout vert.
- **P3** — dérouler les autres clients confidentiels ; garder `product`/`self` en repo cœur.
- **P4** — **registre** des repos clients (`pm.config.yml :: client_repos:` ou manifest) +
  helper `pm clients clone/mount` pour le provisioning d'instance (se branche sur la fédération
  RM1859/RM1860) ; mettre à jour **NORMS** (montage, périmètre de commit par repo client,
  sync-views dangling-safe). Reléguer/retirer l'ancien `ai-projects` monolithique (ou le garder
  comme cœur + registre).

## Estimation

**Petit-moyen.** Le patch d'activation est trivial ; l'essentiel est de l'**ops** (création
repos, droits, split d'historique — rapide) et de la **doc/NORMS**. Faire un **pilote 1 client**
avant tout déroulé.
