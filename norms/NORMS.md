---
schema_version: "2.9.1"
updated: 2026-08-27
---
<!-- ⚠ FICHIER GÉNÉRÉ par scripts/pm-norms-assemble.py depuis norms/src/ — NE PAS ÉDITER À LA MAIN (voir norms/MAINTAINING.md) -->
# Normes de gestion des tâches — v2.9.1
# Normes de gestion des tâches — v2.7.1

## ⚙ KERNEL — lecture obligatoire à chaque session PM

> **Tu lis ce fichier en ENTIER, à chaque session.** Il est court par conception. Il
> contient deux choses : (1) les **tripwires** — règles à respecter en permanence — et
> (2) la **table des déclencheurs** — *quand* ouvrir *quel* module pour le détail.
>
> **Tu n'ouvres un module QUE quand son déclencheur se présente.** Le détail complet de
> chaque règle vit dans `modules/<nom>.md` ; le KERNEL te dit qu'elle existe et quand y
> aller. En cas de doute : le module fait foi sur le **détail**, le KERNEL sur
> l'**obligation d'y aller**.
>
> `NORMS.md` (document complet, ~117 Ko) est un **artefact généré** par
> `pm-norms-assemble.py` à partir de ce KERNEL + des modules — **ne l'édite jamais à la
> main**. Contrat de maintenance : [`../MAINTAINING.md`](../MAINTAINING.md).

## Table des déclencheurs — quand ouvrir quel module

| QUAND (situation que tu reconnais) | → ouvre / applique | Outil canonique |
|---|---|---|
| je résous un chemin PM | `modules/structure-reference.md` (jamais de hardcode) | `pm_paths.PMConfig` |
| je commence à coder un ticket (branche) | `modules/git-mep.md` | `pm-branch-start` |
| je push / crée une MR / projet versionné | `modules/git-mep.md` | `glab` |
| le transport git résiste (SSH/token, submodules), l'API GitLab répond de travers, je prépare une MEP, ou je touche un ticket d'interface | `modules/git-mep-pratique.md` (mode d'emploi, hors précharge) | `pm-mr`, `pm-promote` |
| je livre / teste / mets en preprod (MEP) | `modules/git-mep.md` + `modules/status-workflow.md` | `pm-task-status-update` |
| je livre un changement de SURFACE (outil, flux, cockpit UI, archi/dev) : mettre à jour la doc vivante dans la MÊME MR (Changelog · README · aide cockpit · DEVELOPMENT) | `modules/governance.md` (§ Développement du PM) | — |
| je m'apprête à ouvrir un ticket pour un changement TRIVIAL du repo PM (terme de glossaire, coquille) | `modules/governance.md` (§ Changements sans ticket) — la MR reste due, le ticket non | `pm-mr create --no-ticket` |
| je change un statut de tâche | **tripwire #4** + `modules/status-workflow.md` | `pm-task-status-update` (`--list-next`) |
| je cherche la transition exacte permise, je qualifie en phase d'étude, une transition m'est refusée (assignee-only), ou un ticket revient avec des notes | `modules/status-workflow-pratique.md` (hors précharge) | `pm-task-status-update --list-next` |
| je prends une tâche (passage en_cours) | **tripwire #5** + `modules/status-workflow.md` | `pm-task-status-update` |
| fin de dev / routing vers test | `modules/status-workflow.md` (`requires_agent_test`) | `pm-task-status-update` |
| le demandeur formule une demande (quelle qu'elle soit, même si elle sera ticketée dans la minute) | `modules/session-tooling.md` § « Registre des demandes » | `pm-session-status.py request` |
| un événement notable arrive en séance (secret affiché, action refusée, garde-fou déclenché, outil PM en défaut, décision qui bloque) | `modules/session-tooling.md` § « Notifications importantes » | `pm-session-status.py notify` |
| un ticket me revient (a_corriger / réattribution) | `modules/status-workflow.md` | `redmine-fetch-updates` |
| le ticket a une checklist / desc périmée / done_ratio bouge | `modules/redmine-hygiene.md` | `pm-task-description-update` |
| j'introduis/fais évoluer une donnée ou un artefact partagé Redmine↔PM (champ, vue, template, doc, métrique) | `modules/redmine-sync.md` (principe de parité) | scripts de sync dédiés |
| je produis un livrable documentaire (audit, CDC, spec, roadmap, rapport) | `modules/redmine-sync.md` (format portable : markdown en repo, jamais un artefact LLM-spécifique) | `pm-wiki-sync` |
| je commit / franchis une étape significative | `modules/traceability.md` (note + log + métriques) | `pm-task-report` |
| un échange porte une décision / arbitrage sur la tâche | `modules/traceability.md` (journaliser au fil de l'eau) | — |
| je crée un ticket | **tripwire #7** (CF IA) + estimation | `pm-task-add` |
| je crée un projet / une entité PM | `modules/project-creation.md` (+ bootstrap, memberships) | `pm-project-new`, `pm-project-bootstrap`, `pm-client-new` |
| un projet sert plusieurs clients / implémente un général | `modules/project-modeling.md` | `pm-doctor`, `pm-sync-views` ⚠ |
| je documente un aspect / cahier des charges | `modules/project-modeling.md` (aspects) | — |
| je crée / répare le lien workspace↔PM | `modules/structure-reference.md` | `pm-sync-links` ⚠ |
| je note / cherche un contact d'un client | `modules/project-modeling.md` (§ Contacts) | `pm-client-contact` |
| je me connecte à / référence un environnement | `modules/environments.md` | `ssh_alias` |
| j'écris ou j'édite un aspect `environments.md` (noms d'env, champs, `post_deploy`, chemins de logs) | `modules/environments-reference.md` (hors précharge) | `templates/aspects/common/environments.md` |
| je manipule un secret / credential | **tripwire #11** + `modules/environments.md` | `resolve-secret.sh` |
| début de session PM : péremption des PAT GitLab | `modules/git-mep.md` (rotation J-7) | `pm-token-check` |
| je lie / fais dépendre / parente deux tickets | `modules/task-links.md` | `pm-task-link` |
| une tâche est dans le mauvais projet PM (ou déplacée côté Redmine) | `modules/session-tooling.md` | `pm-task-move` |
| avant une session touchant Redmine / périodiquement | `modules/redmine-reference.md` | `redmine-config-check` |
| micro-tâche (≤ 30 min, sans code) | `modules/status-workflow.md` § flux court | `pm-task-take --no-branch`, `pm-task-add --retro` |
| j'estime / calcule le ROI / priorise | `modules/roi-pricing.md` | `pm-task-add`, `pm-task-tick`, `priority.py` |
| je suis l'orchestrateur (assignation, sous-tâches, propagation) | `modules/collaboration.md` | — |
| je génère les fichiers auto (Changelog/Pistes/Remarques) | `modules/summarizer.md` | — |
| gouvernance : déploiement, versionning de NORMS, distribution des skills | `modules/governance.md` + [`../MAINTAINING.md`](../MAINTAINING.md) | `pm-norms-assemble`, `pm-norms-doctor` |
| j'ajoute/édite un module ou le préchargement d'un rôle (coût de contexte) | `modules/governance.md` | `pm-context-budget` |

⚠ = outil pas encore livré (suivi RM1923) ; en attendant, l'opération manuelle est décrite dans le module.

## Tripwires — à respecter en permanence (dangereux si raté)

Règles dont l'oubli casse silencieusement quelque chose. Énoncé **auto-suffisant** ici ; le détail/rationnel est dans le module indiqué.

1. **Outillage obligatoire.** Toute opération touchant l'**état** d'une tâche, une **branche**, un **repo/submodule** ou un **ticket Redmine** passe par le **script/skill PM dédié**, jamais à la main. Pas d'outil pour une telle opération = **trou à combler** (créer le script), pas une exception manuelle. → `modules/session-tooling.md`
2. **Commit + push systématique.** Après toute modif d'un fichier PM (ai-projects) ou du workspace de code : `git add <chemins explicites>` + commit + **push immédiat**. **Jamais `git add .` / `-A`** ; ne stage et ne commit **que tes propres modifs** (repos partagés souvent dirty en concurrence). → `modules/git-mep.md`
3. **Branche par ticket + livraison par MR — sur les dépôts de CODE.** Coder un ticket = sur une branche `<RMid>-<slug>` tirée de la branche d'intégration (jamais directement dessus) ; renseigner le CF Redmine *GIT Branche*. **Livraison = Merge Request** sur le remote (jamais un merge poussé en direct sur l'intégration), et **la branche distante est CONSERVÉE** après merge (suppression d'une branche distante = accord explicite requis ; autoriser un merge ≠ autoriser une suppression). Ménage des branches mergées **uniquement en local**. **Aucun commit/push direct sur une branche protégée** — intégration (`dev`) **ET** prod (`main`/`master`) : tout passe par branche de ticket + MR, y compris la **promotion `dev`→prod** (modèle 3 branches). Un commit direct sur `main` court-circuite la promotion → divergences et collisions de version ; à **enforcer côté GitLab** (protection de branche : push direct interdit, seul le merge de MR autorisé).
   **Exception — dépôts de DONNÉES PM (`*-core`), RM2440 :** un dépôt portant un `.mmi-pm/` ou `.mmi-pm-client/` **réel** à sa racine (*symlink* = workspace de code, **pas** un core) n'a ni code ni revue possible — l'historique git **est** l'audit. Sa branche de prod accepte le **push direct** (`push=Developer`) : les scripts pm-* y écrivent sans branche ni MR. Pas un contournement : `allow_force_push=false` reste posé, l'historique ne peut que **croître**. → `modules/git-mep.md`
4. **Sync statut MD↔Redmine.** Tout changement de `status` se répercute **dans le même cycle** : Redmine (status_id + note) + frontmatter (`status`, `status_history`, `updated`) + `.log.md`. **Toujours** via `pm-task-status-update.py`, **jamais** un statut « en dur » ; demande les cibles valides via `--list-next`. **Fermeture bloquée par sous-tâche ouverte** : un parent ne passe `ferme` que si **toutes ses sous-tâches sont elles-mêmes fermées** — sinon Redmine **refuse silencieusement** (PUT 204, statut inchangé, faux air de « permission *Edit issues* manquante »). Ne pas s'acharner ni conclure « droits » : vérifier `GET /issues/<id>.json?include=children` (et `allowed_statuses`). → `modules/status-workflow.md`
5. **Prise en charge ⇒ auto-assignation.** Passer une tâche en `en_cours` **implique**, dans le même mouvement, se l'**assigner** (`assigned_to`). Pas d'`en_cours` flottant. → `modules/status-workflow.md`
6. **redmine_id obligatoire.** Toute tâche/projet MD est reliée à son équivalent Redmine ; nom de fichier `RM{id}_…` cohérent avec `redmine_id`. → `modules/status-workflow.md`
7. **Filtrage IA.** Tout ticket créé depuis le système PM porte le CF `IA = "IA"` (posé par les outils au POST). Pas de MD local sans CF IA. → `modules/redmine-reference.md`
8. **Estimation.** Estimer (tokens + temps) **à la création** d'une tâche, et **à la prise** si l'estimation manque. → `modules/roi-pricing.md`
9. **Description vivante.** Si le ticket a une **checklist** ou un état décrit en prose : la tenir à jour **dans la description** (pas seulement en note), + `done_ratio` au fil de l'eau. → `modules/redmine-hygiene.md`
10. **Sécurité prod.** Aucune commande susceptible de modifier/casser la **production** sans **consentement humain explicite pour cette action précise**. Inspecter en lecture seule, proposer la commande exacte, attendre le feu vert ; un accord ne vaut pas pour l'étape suivante. **Point de restauration préalable** : si la cible tourne sur une infra **opensvc / LXC / ZFS**, prendre le **snapshot ZFS du conteneur depuis l'hôte AVANT la MEP** (`om <svc> sync update --rid sync#root_hour`) — il tient lieu de sauvegarde préalable (pas de dump applicatif ad hoc en plus), et son nom se logue avec la procédure de rollback. → `modules/git-mep.md`
11. **Secrets.** Jamais commités, loggués, écrits sur disque ni dans un transcript ; jamais demander le secret de déverrouillage d'un vault (master password, passphrase). → `modules/environments.md`
12. **Traçabilité par étape.** À chaque étape significative : commit + **note Redmine** (détail + réf commit + temps/tokens) + entrée `.log.md`. → `modules/traceability.md`
13. **Jamais d'identifiant séquentiel prédit — RM-id, iid de MR, ou autre.** Ne **jamais** saisir de mémoire un id issu d'une séquence partagée (« dernier vu + 1 ») : Redmine ET GitLab séquencent **globalement à l'instance** (plusieurs agents/projets créent en concurrence), le prochain numéro n'est **pas prévisible** (incidents : RM2142, RM2163, branche 2219→RM2222, merge de la MR !122 d'une autre session). **INTERDIT** (décision Mathieu 2026-07-11) : tout numéro se **capture de la sortie d'un script**, jamais ne s'infère. Outillage : `ID=$(pm-task-add … --porcelain)` ou `--start-branch` (atomique) ; `IID=$(pm-mr create … --porcelain)` ou `pm-mr create --merge` (atomique) ; `pm-mr merge --expect-rm <id>` (garde). Gardes automatiques : refus pm-mr sur branche divergente, hook git pre-push. → `modules/session-tooling.md`
14. **Résolution projet→Redmine précise (jamais par slug nu).** Cibler un projet pour une opération Redmine (sync wiki, note, description, stats…) se fait par référence **non ambiguë** — `client/slug` (ex. `matnat/infra`) ou `redmine.project_id` unique (ex. `matnat-infra`) —, **jamais** par match de slug nu : plusieurs clients partagent un même slug (ex. `infra` chez abatik/calicote/calyclay/matnat/pisceen) et un match « premier arrivé » écrit **silencieusement dans le mauvais projet Redmine**. Un slug **ambigu**, ou un projet **sans `redmine.project_id` en conf** (`meta.yml`), ⇒ **erreur bloquante** (« pas de projet Redmine précis → on n'avance pas »), jamais de choix silencieux. Outillage : `PMConfig.resolve_project_ref(ref, require_redmine=True)`. (incident : RM2410 → `pm-wiki-sync infra` ciblait abatik au lieu de matnat.) → `modules/redmine-reference.md`

Les tripwires **structurels** (propriété exclusive du fichier, optimistic locking, journal append-only) sont énoncés juste en dessous, suivis de la colonne vertébrale (cascade, nommage, schéma frontmatter, énumérations).

## Propriété, verrou & journal — tripwires structurels

### Principe fondamental

**Redmine est le mutex. Les fichiers MD sont le contexte de travail.**

L'assignation d'un ticket Redmine à un agent lui confère la **propriété** du fichier MD correspondant (coordination de 1er niveau) ; en multi-dev, l'accès concurrent réel est **sérialisé par ressource** (`flock`), pas garanti par un unique écrivain.

L'inférence LLM est déjà distribuée par nature (appels API vers Anthropic). Ce qui doit être coordonné, c'est uniquement l'accès aux fichiers.

**Multi-utilisateur (v2.0.0) :** données communes partagées (groupe `pm`), accès concurrent **sérialisé par ressource** (`flock`), karl = admin via `sudo` humain. → `modules/collaboration.md`.

### Règles d'écriture

| Fichier | Orchestrateur | Worker assigné | Autres workers | Reviewer |
|---|---|---|---|---|
| `RM{id}.md` (tâche assignée) | lecture | **R+W** | lecture | lecture |
| `RM{id}.md` (tâche parente) | **R+W** | lecture | lecture | lecture |
| `RM{id}.log.md` | append | append | lecture | append |
| `project.md` | **R+W** | lecture | lecture | lecture |
| `NORMS.md` | lecture | lecture | lecture | lecture |

### Protocole optimistic locking

Filet inter-machine contre les écritures simultanées ; complète les verrous `flock` (même machine). Rare si propriété et verrous sont respectés.

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
2. Client     : {entity_client_dir}/*.md + {entity_memory_dir}/*.md
3. Projet     : {project_dir}/*.md + {docs_dir}/*.md + {project_memory_dir}/*.md
4. Tâche      : paths.task_file + paths.task_log_file
```

(Chemins résolus via `pm.config.yml` — par défaut : `{projects_root}/clients/{C}/...`)

Chaque niveau **complète** ou **surcharge** le précédent selon les règles ci-dessus.

## Nommage des fichiers

| Élément | Format |
|---|---|
| Tâche | `RM{id}_{titre-en-kebab-case}.md` |
| Journal | `RM{id}_{titre-en-kebab-case}.log.md` |
| Overview projet | `project/overview.md` |
| Overview client | `client/overview.md` |

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
- `requires_agent_test` — `default` (défaut) | `oui` | `non` | `demander` : conditionne la
  passe agent-testeur en fin de dev (cf. § « Passe agent-testeur indépendante »). Mappé sur
  le CF Redmine 27. Absent ⇔ `default`.

## Valeurs énumérées

### type
`audit` | `feature` | `bugfix` | `refactoring` | `documentation` | `security` | `performance` | `infrastructure` | `configuration` | `database` | `design` | `research` | `maintenance` | `assistance`

### status
`a_etudier_chiffrer` | `etude_chiffrage_en_cours` | `etude_chiffrage_a_valider` | `a_faire` | `en_cours` | `a_tester_dev` | `a_tester_demandeur` | `a_mep` | `en_mep` | `en_pause` | `a_corriger` | `ferme`

`a_tester_verifier` est **déprécié** (≤ v1.18.0) — alias en lecture de
`a_tester_demandeur`, normalisé par les scripts.

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

### target_env
`null` | `local` | `dev` | `test` | `staging` | `prod` | `demo` | `qa` | `sandbox` | `<custom-kebab-case>`

Doit correspondre à un `environments[].name` du `project/environments.md` (ou
`client/environments.md` en cascade). Custom autorisé si le projet a un env spécifique
(`staging-eu`, `prod-canary`…). `preprod` reste accepté comme **alias** de `staging`
(cf. § Environnements) mais `staging` est la valeur canonique à privilégier.

## Journal (fichier .log.md)

Format append-only — ne jamais modifier rétroactivement. Chaque entrée :

```markdown
## 2026-04-26T14:32 — agent-scraper (claude-sonnet-4-6)
Tokens : 3 200 | Durée : 15 min

Résumé de ce qui a été fait...
```

> 📂 **Module `structure-reference` — quand lire ceci :** je résous un chemin PM · j'inspecte l'arbo des repos · je me demande dans quel dépôt committer (code vs structure) · je crée/répare le lien workspace↔PM.
> **Outils :** `pm_paths.PMConfig`, `pm-sync-links`⚠ · **Préchargé par :** worker-infra.

### Anatomie d'un projet — le core, `repos/` et `envs/`

**Un projet est défini par un dossier `.mmi-pm`.** Ce dossier vit dans le **core** du
projet : le dépôt git à la racine du workspace, qui ne **révisionne que `.mmi-pm/`** par
défaut (tout le reste — code, données, démos — y est gitignoré). Le core porte donc la
**définition du projet** (`project/`, `docs/`, `tasks/`, `memory/`) et rien d'autre.

Autour du core, deux dossiers structurent le **code** :

```
<workspace>/                     # = CORE du projet — dépôt git, remote `<Projet>-core.git`
  .mmi-pm/                       # LE projet : project/ docs/ tasks/ memory/  (seul révisionné par le core)
  repos/
    <repo>.git                   # dépôt de CODE, bare — la SOURCE
  envs/
    <repo>-dev                   # WORKTREE tiré de repos/<repo>.git — env d'intégration
    <repo>-rm<RMid>              # WORKTREE de ticket (pm-branch-start --worktree, pm-env-session create)
    <repo>-rm<RMid>-s<seq>       # … suffixé UNIQUEMENT si le canonique sert déjà une autre branche
  …                              # data/, démos, .claude/ … gitignoré par le core
```

Les `envs/*` sont des **worktrees** d'un même dépôt bare `repos/<repo>.git` (cf.
`git-mep` pour le workflow branche/worktree par ticket).

**Nommage des worktrees — convention unique `<repo>-rm<RMid>` (RM2523).** Le nom
dérive du **dépôt** (`repos/<repo>.git`), jamais du worktree depuis lequel on
lance la commande. Le faire dériver du worktree courant — ce que faisait
`pm-branch-start` — concatène son nom à chaque création en cascade et produit des
`<repo>-rm2356-2373-s1-2385-s1-2323-s20-…` (7 cas sur le workspace PM en 2026-08).
Même règle pour le champ `git.repo` du frontmatter : il porte le nom canonique du
dépôt, pas celui d'un worktree ; les valeurs héritées sont normalisées à
l'écriture. Le suffixe `-s<seq>` ne sert qu'à départager deux sessions sur un même
ticket. Un worktree se **résout par sa branche** (`<RMid>-<slug>`), jamais par son
nom deviné — c'est ce qui rend le nommage indifférent à l'outillage.

**Deux dépôts, deux destinations de commit — ne jamais les confondre :**

| Ce que tu commites | Où | Dépôt / remote | Protection de la branche de prod |
|---|---|---|---|
| **Travail / code** (src, tests, config appli) | un **worktree** sous `envs/` | dépôt de code (`repos/<repo>.git` → ex. `worm-web-orm`) | push **personne** → branche de ticket + **MR** |
| **Structure / projet** (tâches, docs, overview, mémoire — tout `.mmi-pm/`) | le **core** (racine du workspace) | dépôt core (ex. `Worm-core.git`) | push **Developer** → écriture **directe** des scripts pm-* |

Les commits de code partent vers le remote du **code** ; les auto-commits PM (`pm-*`,
qui ne touchent que `.mmi-pm/`) partent vers le remote du **core**. **Corollaires
structurels** (invariants pour l'outillage) :

- un dépôt porteur d'un `.mmi-pm` à sa racine **est un core**, **jamais** une cible de
  branche de code — le code se branche dans un worktree `envs/` tiré de `repos/` ;
- un worktree `envs/` n'est **jamais** l'endroit où l'on commite une tâche/doc PM ;
- le marqueur doit être un **dossier réel** : dans un workspace de code, `.mmi-pm` est
  un **symlink** vers le dossier PM centralisé — ce workspace n'est **pas** un core et
  sa branche de prod reste protégée comme du code (RM2440). C'est le test qui distingue
  les deux régimes de protection ci-dessus, implémenté une seule fois dans
  `pm_git.is_core_repo()` et réutilisé par `pm-protect`.

La colonne « protection » est posée par `pm-protect` (cf. `git-mep` § Enforcement
GitLab) ; `allow_force_push=false` s'applique aux **deux** colonnes — quel que soit le
régime, l'historique ne peut que croître.

**Même motif au niveau entité/client** : une entité a son propre **`.mmi-pm-client`**
(core client), porté par son dépôt dédié.

### Repo project-management (système, public)

```
project-management/                   # racine : pm.config.yml :: roots.pm_dir
  pm.config.yml                       # config de chemins (résolution centralisée)
  pm.config.local.yml                 # surcharge locale (gitignored, optionnel)
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
    pm_paths.py                       # lib de résolution de chemins (PMConfig)
    validate-task.py
    priority.py                       # ordonnancement par ROI
    pm-dashboard.py                   # CLI dashboard (statuts, ROI, en cours, activité)
    pm-project-bootstrap.py           # instancie les bootstrap-tasks dans un projet
    redmine-test.py                   # test de connexion API Redmine
    redmine-fetch-task.py             # fetch ticket Redmine → génère le MD
    redmine-fetch-updates.py          # récupère les nouveautés depuis le dernier check
    redmine-post-note.py              # poste une note (+ statut + assignation) sur un ticket
    invoke.md
    cron.example.sh
```

### Repo projets (index centralisé)

Racine : `pm.config.yml :: roots.projects_root` (résolu depuis `$PROJECTS_PATH`).
Structure interne définie par les patterns de `paths:` — la représentation
ci-dessous montre la **résolution par défaut**.

> **⚠ Sens du lien inversé — `projects_root` est un INDEX, plus le stockage.**
> Historiquement cette arbo **contenait** les données PM et le `.mmi-pm` de chaque
> workspace y **pointait** (symlink entrant). Le modèle canonique actuel est
> **inversé** : la source de vérité est le **`.mmi-pm` du core** de chaque projet (cf.
> « Anatomie d'un projet » ci-dessus), et chaque
> `projects_root/{entity_projects_dir}/<P>` est un **symlink SORTANT** vers ce
> `.mmi-pm`. `projects_root` est donc un **index** de liens vers les cores — maintenu
> par `mmi-pm index add|rebuild` (reconstruit depuis les emplacements canoniques
> `.mmi-pm` / `.mmi-pm-client`) —, pratique pour que l'orchestrateur scanne tous les
> projets d'un coup (`cfg.iter_projects()`), mais ce **n'est plus** l'endroit où vivent
> les tâches/docs. L'arbre par défaut ci-dessous décrit donc ce que chaque core expose
> **à travers** son lien d'index, pas un stockage central.

```
{projects_root}/                      # = $PROJECTS_PATH (repo ai-projects)
  README.md
  {entities_dir}/                     # = projects_root/clients
    {entity}/                         # entité = client | product | self (slug)
      {entity_client_dir}/            # = entity/client  — cahier des charges
        overview.md                   # OBLIGATOIRE — frontmatter + sommaire
        hosting.md                    # aspect — optionnel
        contracts.md                  # aspect — optionnel
        ...                           # tout aspect pertinent
      {entity_memory_dir}/            # = entity/memory  — mémoire structurée (agents)
      Changelog.md                    # AUTO — activité agrégée
      Pistes.md                       # AUTO — idées non décidées
      Remarques.md                    # AUTO — observations factuelles
      {entity_projects_dir}/          # = entity/projects
        {project}/                    # = entity_projects_dir/{project-slug}
          {project_dir}/              # = project/project  — CANONIQUES (mathieu-pm, via mmi-pm)
            overview.md               # OBLIGATOIRE — frontmatter + sommaire/index des aspects
            environments.md           # aspect canonique — optionnel (consommé par l'outillage)
          {docs_dir}/                 # = project/docs  — aspects LIBRES (wiki-syncés, group-writable)
            hosting.md                # aspect — optionnel
            stack.md
            data-model.md
            workflows.md
            audience.md               # exemples — uniquement les aspects pertinents
            ...
          {project_memory_dir}/       # = project/memory  — mémoire spécifique projet
          Changelog.md                # AUTO
          Pistes.md                   # AUTO
          Remarques.md                # AUTO
          {tasks_dir}/                # = project/tasks
            RM{id}_{titre-kebab}.md         # = paths.task_file
            RM{id}_{titre-kebab}.log.md     # = paths.task_log_file
```

**Contacts d'un client** (`meta.yml :: contacts[]`, écriture par
`pm-client-contact`) : voir `modules/project-modeling.md` — c'est de la
modélisation d'entité, pas de la résolution de chemins (RM2755).

### Workspace projet — symlinks bidirectionnels `.mmi-pm` ↔ `workspace`

> **⚠ Section legacy — décrit l'ancien modèle (symlink `.mmi-pm` *entrant*).** Le
> modèle canonique actuel est « Anatomie d'un projet » ci-dessus : `.mmi-pm` est un
> **vrai dossier** dans le core, et c'est l'**index** `projects_root` qui porte le
> symlink **sortant**. Le lien inverse `workspace` (côté core) survit sous une forme
> triviale — `.mmi-pm/workspace → ..` (le core EST le workspace). On conserve cette
> section pour les workspaces pas encore migrés et pour la mécanique de résolution
> cross-tree en fin de section, toujours valable.

Chaque projet a **deux emplacements** distincts mais liés :

| Emplacement | Contenu | Repo git |
|---|---|---|
| `{workspace_dir}/` — variable selon projet, ex: `/zfs/workspaces/<P>/` ou `/zfs/workspaces/<entity>/<P>/` | Code source du projet | repo de code (ex: `iprospective/dev/<P>`) |
| `paths.project` (par défaut `{projects_root}/clients/<C>/projects/<P>/`) | Cahier des charges, tâches, mémoire | `ai-projects` |

Les deux emplacements se référencent **mutuellement** par symlinks (chemins
absolus, définis dans `pm.config.yml :: paths.reverse_link` et
`paths.workspace_link`) :

```
{workspace_dir}/.mmi-pm    → paths.project           # paths.reverse_link
paths.project/workspace    → {workspace_dir}         # paths.workspace_link
```

**Création (les deux symlinks ensemble) :**
```bash
# Côté workspace (code) :
ln -s "$(python3 -c 'from pm_paths import PMConfig; \
  print(PMConfig.load().path("project", entity="<C>", project="<P>"))')" \
  "$WORKSPACE_DIR/.mmi-pm"

# Côté PM (référence inverse) :
ln -s "$WORKSPACE_DIR" "$(python3 -c '…path("workspace_link", …)…')"
```

(Un futur `pm sync-links` automatisera ces deux opérations.)

**Bénéfices :**
- Un agent travaillant dans le workspace voit code ET tâches/docs (`.mmi-pm/project/`,
  `.mmi-pm/docs/`, `.mmi-pm/tasks/`) ; un symlink de confort `<workspace>/docs → .mmi-pm/docs`
  expose les aspects libres à la racine du code
- Un agent travaillant côté PM (dans `paths.project`) accède directement au code via
  `workspace/` — utile pour consulter une stack, un commit, un fichier en cours de
  modification
- Bidirectionnel : si le dossier d'un côté est déplacé, on a un point de repère côté
  opposé pour rétablir le lien sans chercher
- La centralisation est préservée (l'orchestrateur scanne `cfg.projects_root` directement,
  sans suivre `workspace/`)

**Conventions :**
- Le symlink `.mmi-pm` côté workspace est **caché** (préfixe `.`) pour ne pas polluer
  l'arborescence du code
- Le symlink `workspace` côté PM est **dans la racine du dossier projet PM** (au même
  niveau que `project/`, `tasks/`, `memory/`)
- Les scripts d'itération (validator, dashboard, summarizer) doivent **ignorer**
  les symlinks `workspace` (utiliser `find -P` ou `! -type l`, ou `cfg.iter_projects()`
  qui filtre déjà les symlinks) pour ne pas se perdre dans le code
- Les deux symlinks pointent en chemins **absolus** (les paths workspace/PM ne sont
  pas systématiquement co-localisés ; `realpath` doit fonctionner depuis n'importe où)

**Résolution de chemins cross-tree** (ex: cascade vers le client) :
Ne pas utiliser `.mmi-pm/../../` (résolution logique non fiable des symlinks). Utiliser
la lib + le champ `client:` du frontmatter de `project/overview.md` :

```python
client_dir = cfg.path("entity", entity=client_slug)
```

## Structure des dossiers

## Configuration des chemins (`pm.config.yml`)

Tous les chemins du système (racine du repo PM, racine du repo projets,
emplacement des entités, des projets, des tâches, des symlinks de liaison
code ↔ PM) sont **paramétrés** dans `pm.config.yml` à la racine du repo PM.

**Objectif** : pouvoir déplacer le repo PM, déplacer le repo projets, ou
réorganiser la structure interne **sans toucher au code des scripts ni à la
doc des agents**.

**Lib** : `scripts/pm_paths.py` expose `PMConfig.load()` qui charge la config,
résout `${VAR}` depuis `.env`, et fournit `.path(key, **kwargs)` pour résoudre
n'importe quel chemin via les patterns définis. Tous les scripts du repo
**doivent** passer par cette lib — jamais de concaténation manuelle ni de
hardcode `clients/`.

**Patterns standards** (clés de `paths:` dans `pm.config.yml`) :

| Clé | Résolution par défaut |
|---|---|
| `entities_dir` | `{projects_root}/clients` |
| `entity` | `{entities_dir}/{entity}` |
| `entity_client_dir` | `{entity}/client` |
| `entity_memory_dir` | `{entity}/memory` |
| `entity_projects_dir` | `{entity}/projects` |
| `entity_used_dir` | `{entity}/projects_used` |
| `project` | `{entity_projects_dir}/{project}` |
| `project_dir` | `{project}/project` |
| `docs_dir` | `{project}/docs` |
| `project_memory_dir` | `{project}/memory` |
| `tasks_dir` | `{project}/tasks` |
| `task_file` | `{tasks_dir}/RM{id}_{slug}.md` |
| `task_log_file` | `{tasks_dir}/RM{id}_{slug}.log.md` |
| `workspace_link` | `{project}/workspace` |
| `reverse_link` | `{workspace_dir}/.mmi-pm` |

**Override local** : `pm.config.local.yml` (gitignored) peut surcharger
n'importe quelle clé pour un déploiement spécifique.

**Usage côté script** :
```python
from pm_paths import PMConfig
cfg = PMConfig.load()
cfg.projects_root                                      # Path
cfg.path("task_file", entity="lemathou", project="x", id=42, slug="foo")
for ent, proj, _ in cfg.iter_projects(entity=None): ...
cfg.find_task(rm_id)                                   # Path | None
cfg.find_project_by_redmine_id(rm_proj_id)             # (Path, Path) | (None, None)
```

**Usage côté doc / agents** : les chemins sont nommés par leur pattern
logique (ex: `paths.task_file` pour le fichier d'une tâche), non par leur
expansion filesystem. La résolution par défaut reste écrite ci-dessus pour
référence humaine.


### Le pont d'onboarding des workspaces (RM1892)

Un agent lancé dans un workspace de code n'a, par défaut, **aucun contexte PM**. Il le
reçoit d'un fichier unique posé à la **racine des workspaces**, lu par remontée
d'arborescence depuis n'importe quel sous-dossier :

| Fichier | Rôle |
|---|---|
| `<racine>/AGENTS.md` | le pont — vendor-neutral (opencode & autres) |
| `<racine>/CLAUDE.md` → `AGENTS.md` | symlink : Claude Code ne lit que `CLAUDE.md`, mais suit les liens |

Il est **conditionnel** : « si ton workspace a un `.mmi-pm`, tu es un worker PM — résous-le,
lis le KERNEL, applique le protocole ; sinon ces règles ne te concernent pas ». Un fichier
par projet serait à la fois redondant et à maintenir ; la remontée d'arborescence couvre
les projets présents **et futurs**.

Ce fichier est **hors git** : c'est un artefact de provisioning, propre à l'instance. Sa
référence versionnée est `templates/workspace-AGENTS.md`, et le déploiement est outillé
(`pm-workspace-bridge.py` — contrôle, `--install`, `--update`). Le bloc délimité
`BEGIN/END INSTANCE` porte ce qui est propre à la machine (chemins, hôtes, transport git) :
`--update` rafraîchit le générique et **préserve ce bloc**, ce qui permet de faire évoluer
l'onboarding sans faire perdre à une instance ce qu'elle sait d'elle-même.
> 📂 **Module `session-tooling` — quand lire ceci :** je cherche quel outil PM utiliser pour une opération touchant l'état d'une tâche/branche/repo/Redmine.
> **Outils :** tous les `pm-*` · **Préchargé par :** tous.

## Cheatsheet outillage (RM2367, CDC RM2316 § S6)

**`norms/CHEATSHEET.md`** (généré : `pm-norms-assemble.py cheatsheet`, ≤ 1 200
tokens) : 1 ligne par outil du quotidien + les flux nominaux (take → deliver,
porcelain, lectures ciblées). **Le lire UNE fois en début de session** remplace
les `--help` répétés (300–600 tokens chacun) ; `--help` reste court par défaut,
`--help-full` donne le pavé complet.

> **Garde de périmètre (RM2274).** Les outils MUTANTS (`pm-task-link`, `-status-update`,
> `-comment`, `-protocol`, `-description-update`) REFUSENT d'écrire sur un ticket d'un
> autre projet que le workspace courant si l'id n'a jamais été vu dans la session —
> l'empreinte d'un id prédit (tripwire #13). Écriture cross-projet voulue : `--cross-project`.

## Outillage obligatoire en session PM — v1.35.0

En **session PM** (workspace PM-tracké via `.mmi-pm`, ou travail dans le repo PM), toute
opération touchant à l'**état des tâches, aux branches git, aux repos/submodules ou aux
tickets Redmine** passe par les **skills/scripts PM dédiés** — **jamais à la main**. C'est
ce qui garantit la cohérence Redmine ↔ MD ↔ worklog de session et l'application des
couplages NORMS (auto-assignation, notes, `status_history`, logs, filigrane IA, temps/tokens).

**Règle anti-trou** : si une opération de cette nature a un outil, l'utiliser ; si elle n'en
a pas, c'est un **trou d'outillage à combler** (créer le script/skill) — pas une exception à
faire à la main. En particulier, toute opération qui **amende l'état d'une tâche** est
branchée derrière `pm-task-status-update.py` (**source unique des transitions**), qui propage
Redmine + MD + log + worklog de session. Le worklog de session (`pm-session-status.py`) est
alimenté **automatiquement** par les scripts qui modifient l'état des tâches (via
`pm_session_hook.py`) ; cf. RM1875.

### Couverture actuelle (à compléter au fil des trous identifiés)

| Domaine | Opération | Outil canonique |
|---|---|---|
| Tâche | créer | `pm-task-add.py` · `mmi-pm-task-add` (`--porcelain` = id nu sur stdout) |
| Tâche | changer le statut | `pm-task-status-update.py` · `mmi-pm-task-status-update` |
| Tâche | commenter | `pm-task-comment.py` · `mmi-pm-task-comment` |
| Tâche | lier (relates/depends/blocks) | `pm-task-link.py` · `mmi-pm-task-link` |
| Tâche | **déplacer vers un autre projet PM** (fiche + `.log` + `.reporting`, et `project_id` Redmine vérifié par relecture) | `pm-task-move.py <id> --to <client>/<projet>` (RM2866) |
| Tâche | description / checklist | `pm-task-description-update.py` |
| Tâche | estimation (CF prévisionnels) | `pm-task-metrics-push.py --estimate` |
| Tâche | mesure temps/tokens (hook) | `pm-task-tick.py` |
| Tâche | report conso → Redmine (time_entries + CF17) | `pm-task-report.py` |
| Donnée PM | commit+push des écritures de scripts | *(automatique — `pm_git.autocommit`, RM1834 ; **silencieux si ça passe**, RM2440 ; `--no-commit` pour débrayer)* |
| Repo | protection de branches (code **ou** core) | `pm-protect.py` (`--repo` · `--all-cores`) |
| Instance | pont d'onboarding des workspaces (`AGENTS.md` + `CLAUDE.md`) | `pm-workspace-bridge.py` (nu = contrôle · `--install` · `--update`, RM1892) |
| Repo | promouvoir intégration → prod | `pm-promote.py` — ⚠ **transition** (RM2440), hors flux nominal |
| Tâche | démarrer la branche de ticket (+ CF GIT Branche) | `pm-branch-start.py` (`--worktree --print-cd` = chemin nu à `cd`) |
| Tâche | se (re)placer dans le worktree du ticket | `pm-task-cd.py` — `cd "$(pm-task-cd.py <id>)"` (RM2240) |
| Projet | cohérence des paires cross-projet (used_by/provided, implements) | `pm-doctor.py` |
| Tâche | sync depuis Redmine | `pm-task-sync.py` · `mmi-pm-task-sync` |
| Tâche | lister / afficher | `pm-task-list.py`, `pm-task-show.py` |
| Projet / client | créer / bootstrap | `pm-project-new.py`, `pm-project-bootstrap.py`, `pm-client-new.py` |
| Ticket Redmine (bas niveau) | note / fetch / tag IA / config | `redmine-post-note.py`, `redmine-fetch-*.py`, `redmine-tag-ia.py`, `redmine-config-check.py` |
| Session | worklog d'avancement | `pm-session-status.py` · `mmi-pm-session-status` |
| Session | **événement notable** (secret exposé, refus, garde-fou, outillage en défaut, décision bloquante) | `pm-session-status.py notify` |
| Session | **demande du demandeur** (avant même de savoir si elle sera ticketée) | `pm-session-status.py request` |
| Session → tâche | **consigner les décisions** (questions tranchées / restées sans réponse) dans le journal du ticket | `pm-decisions.py persist <id>` |
| **Branches / repos / submodules** | créer branche par ticket, commit+push conventionné, base de version | **⚠ trou — aucun outil dédié** (cf. § « Branche de travail par ticket », § « Commit + push systématique ») |

## Notifications importantes de session (RM2466)

Un incident rencontré en séance se perd au défilement : **consigne-le sur-le-champ**
(pas « à la fin »), `pm-session-status.py notify "<fait>" --kind <type> [--ref RM<id>]`.
Types : `secret` (→ `critical` ; la **rotation** reste à faire), `refus`, `garde-fou`,
`outillage`, `decision`. Un fait notable et actionnable, jamais un commentaire — un
canal noyé ne sera pas lu.

**Et referme-la quand elle est traitée** (RM2715) : `notify --resolve <n> --ticket
RM<id>`. Une notification dit ce qu'il reste à faire ; laissée telle quelle après
coup, elle porte une consigne périmée (« ticket à ouvrir » alors qu'il l'est) et
use la crédibilité du canal. Résoudre la sort du backlog **sans** la supprimer —
elle reste en archive avec le ticket qui l'a portée. `--clear`, lui, DÉTRUIT :
ce n'est pas le geste courant. Mode d'emploi : skill `mmi-pm-session-status`.

## Registre des demandes (RM2621)

Une demande formulée en séance n'existe que dans le fil : non ticketée
sur-le-champ, elle disparaît au premier défilement.

**Règle — enregistre CHAQUE demande dès réception**, avant de savoir si elle
sera ticketée : `pm-session-status.py request "<la demande>"`. Puis, quand son
sort est connu : `request --set <n> --status ticketee --ticket RM<id>` (ou
`repondu` / `annulee` / `fusionnee --merged-into <n>`). Enregistrer coûte une
ligne ; oublier ne laisse aucune trace.

Ne filtre pas à la réception : « fais une sous-tâche » fait 19 caractères et
c'est une demande. En cas de doute, enregistre — une entrée en trop se classe,
une demande perdue ne se retrouve pas. Contrôle : `request --audit` compare le
registre au transcript. Mode d'emploi : skill `mmi-pm-session-status`.

**N'enregistre pas ce qui ne vient pas du demandeur** (RM2635) : résumé de
compaction réinjecté dans le fil, collage de console renvoyé à TA demande,
sortie de commande. Ce ne sont pas des demandes et ils noient les vraies. Si
l'une s'est glissée dans le registre, elle se range en `non_demande` — pas en
`annulee` : personne n'a rien annulé, et ranger le bruit sous un statut faux
rend le registre inexploitable pour la question à laquelle il sert à répondre.

### Idiomes fréquents (évite de relancer `--help` à chaque session)

- **Contenu long / multi-ligne via stdin** : `pm-task-comment <id> --note - < note.md`,
  `redmine-post-note <id> --note -`, `pm-task-add --description -` (ou
  `--description-file <path>`), `pm-task-description-update <id> --set-from-file <path>`.
  Passer par stdin/fichier plutôt qu'un argument quoté évite AUSSI la protection
  Bash « newline + `#` » de Claude Code (validation à répétition sur les arguments
  multi-lignes contenant un dièse).
- **Transitions valides depuis le statut courant** : `pm-task-status-update <id> --list-next`
  (au lieu de deviner le flow d'états).
- **Auto-assignation** : `en_cours` auto-assigne au porteur (`--assign-to me` implicite) ;
  `--assign-to <id|me|author>` pour forcer, `--no-assign` pour débrayer.
- **Détection de projet** : si la détection cwd échoue ou est ambiguë,
  `--project entity/project` explicite (`pm-task-add`, `pm-task-list`, …).
- **Répétition sans risque** : `--dry-run` sur `pm-task-add`, `pm-task-status-update`,
  `pm-task-sync` — voir le diff avant d'écrire.
- **Script lancé depuis un worktree sans `.env`** : préfixer
  `PM_CORE_DIR=<racine du repo PM actif>` (sinon « ERREUR : aucun .env trouvé »).

### Capture d'un RM-id fraîchement créé — jamais de prédiction (tripwire #13)

La séquence des ids Redmine est **globale à l'instance** : plusieurs agents et
plusieurs projets créent des tickets **en concurrence**. Le prochain id n'est donc
**jamais prévisible** — « dernier id vu + 1 » est une **erreur structurelle** (deux
incidents en deux jours : RM2142 puis RM2163, prises/branches/statuts posés sur le
mauvais ticket, à corriger après coup).

**Règle** : après une création, **capturer** l'id depuis la sortie de l'outil, ne
jamais le retaper de mémoire. `pm-task-add.py` expose **`--porcelain`** (alias
`--id-only`) qui n'imprime que **l'id nu sur stdout** (tous les logs partent sur
stderr) — la capture devient triviale et fiable :

```bash
ID=$(pm-task-add --title "…" --type feature --porcelain)   # ex. → 2170
pm-task-status-update "$ID" en_cours
pm-branch-start "$ID" --take
pm-task-link add "$ID" 1834 --type relates
```

Toute commande enchaînée **consomme la variable `$ID`**, jamais un littéral. Sans
`--porcelain`, capturer sur le format verbeux : `ID=$(pm-task-add … | grep -oE 'RM[0-9]+' | head -1)` (moins robuste — préférer `--porcelain`).

> 📂 **Module `project-modeling` — quand lire ceci :** je crée/range un projet ou une entité · partage cross-client · relation implements · je documente un aspect (CDC) · je note les contacts d'un client.
> **Outils :** `pm-client-new`, `pm-doctor` · **Préchargé par :** worker-analyst.

## Types d'entités

Le dossier `paths.entities_dir` (par défaut `{projects_root}/clients`) regroupe
**3 types d'entités**, distingués par le champ `type` du frontmatter
`{entity_client_dir}/overview.md` :

| `type` | Sémantique | Exemples |
|---|---|---|
| `client` (défaut) | Entité commerciale tierce qui commande des prestations | `lemathou` (perso/freelance Mathieu), `pisceen`, `calicote` |
| `product` | Écosystème produit dont iprospective développe des modules (génériques) ou maintient une instance interne | `redmine`, `dolibarr`, `prestashop`, `symfony` |
| `self` | Entité où l'on est client de soi-même : outils internes, scripts propres, projets perso non commerciaux | `iprospective` (entreprise freelance), `lemathou` aussi (projets perso de Mathieu) |

Cohérent avec l'arborescence workspace : `/zfs/workspaces/<entité>/` existe au même niveau
pour chaque entité, qu'elle soit `client`, `product` ou `self`.

**Règle d'arbitrage** lorsqu'un projet pourrait vivre sous plusieurs entités (ex: un
module Dolibarr générique utilisé par plusieurs clients) :

- Si **commandé/financé par un client** → sous ce client (`paths.project` avec `entity=<client>`)
- Si **générique** (marketplace, communauté, usage interne propre) → sous l'écosystème produit (`paths.project` avec `entity=<product>`)
- Si **outil interne** non rattaché à un produit tiers → sous `self` (`paths.project` avec `entity=iprospective`)

Suivre l'engagement de livraison et la responsabilité des données.

## Contacts d'un client — `meta.yml :: contacts[]` (v1.69.0, RM2702)

Les personnes d'un client vivent dans le `meta.yml` de son core
(`.mmi-pm-client/meta.yml`), et **uniquement** là. Écriture par
`pm-client-contact.py` (`add` / `list` / `set` / `remove` / `mark-internal` /
`import-redmine`) — jamais à la main (tripwire #1).

```yaml
contacts:
  - last_name: Dupont              # NOM de famille
    first_name: Claire             # prénom
    email: claire@exemple.fr       # identifie la fiche (clé de `set` / `remove`)
    phone: "+33 6 12 34 56 78"     # CHAÎNE : le « + » et les zéros de tête comptent
    role: technique                # owner | decideur | technique | facturation | autre
    title: Gérant                  # fonction EN CLAIR — `role` est une catégorie, pas un titre
    internal: true                 # posé AUTOMATIQUEMENT sur nos propres adresses
```

Deux pièges, tous deux rencontrés en production :

- **`internal`** marque **nos** adresses (`iprospective.fr`…). Le gabarit de création
  en pose une chez **chaque** client : elle n'identifie donc aucun client et ne doit
  jamais servir à l'identifier — router un email entrant sur cette base enverrait tout
  notre courrier chez un client au hasard (cf. routage RM2669).
- Une fiche **entièrement vide** (`{name: "", email: "", role: owner}`) est un résidu
  de gabarit, pas un contact : les outils l'ignorent.

Une **boîte de service** (« Service informatique », « comptabilité ») est un contact
légitime sans nom propre : on renseigne `title` + `email`, sans `last_name`/`first_name`.

Le champ historique `name` (nom complet en un bloc) reste **lu en repli** tant que
toutes les fiches n'ont pas été reprises ; les nouvelles écritures utilisent
`last_name` / `first_name`.

> Un **annuaire de contacts indépendant** des clients (une personne rattachée à
> plusieurs clients/projets, avec un rôle par rattachement) est à l'étude — RM2703.
> Tant qu'il n'existe pas, `contacts[]` reste la source unique.

## Partage cross-client (used_by_clients / provided_by)

Un projet rangé sous une entité (`product` notamment) peut être **utilisé par plusieurs
clients**. Plutôt que de dupliquer le projet ou de jouer avec des symlinks à la main,
on utilise deux champs dans le frontmatter `project/overview.md` :

| Champ | Sens | Côté |
|---|---|---|
| `used_by_clients: [<slug>, ...]` | Liste des entités qui consomment ce projet | déclaré côté **fournisseur** (ex: module Dolibarr générique liste `pisceen, calicote, calyclay`) |
| `provided_by: <client>/<projet>` | Pointeur vers le projet fournisseur | déclaré côté **consommateur** (ex: un projet client qui s'appuie sur le module) |

Ces deux champs sont **redondants par construction**, pour permettre la lecture dans les
deux sens sans scan inverse coûteux. `scripts/pm-doctor.py` valide la cohérence des paires.

**Source de vérité** : le frontmatter, pas l'arborescence filesystem. Le chemin
canonique d'un projet est toujours `paths.project` (`entity=<owner>`,
`project=<projet>`).

**Vue cross-client (navigation humaine uniquement)** : un dossier `paths.entity_used_dir`
(par défaut `{entity}/projects_used`, au même niveau que `entity_projects_dir`, **pas**
un sous-dossier) peut contenir des symlinks relatifs vers les projets fournisseurs.
Ces symlinks sont **générés** par un script (`pm sync-views`) à partir des
`used_by_clients[]`, jamais édités à la main.

**Règles cross-client :**
- La cascade des aspects reste **mono-client** : un projet hérite uniquement de son
  client `client:`, jamais des clients listés dans `used_by_clients[]`.
- Tous les chemins dans le frontmatter (`outputs[]`, etc.) sont **canoniques**
  (résolus via `paths.project` avec l'`entity` propriétaire), jamais via `entity_used_dir`.
- Les scripts d'itération doivent utiliser `find -P` (ou `! -type l`) et **ne pas suivre
  les symlinks** dans `projects_used/`. Sinon double-comptage.
- L'édition se fait toujours via le chemin canonique. `projects_used/` est en lecture
  pour les humains.
- Suppression d'un usage : retirer le client de `used_by_clients[]` côté fournisseur ET
  `provided_by` côté consommateur si présent. `pm sync-views` nettoie les symlinks
  orphelins.

## Relation « implémentation » entre projets (implements / implemented_by) — v1.38.0

Distincte du partage cross-client ci-dessus. Un projet peut être l'**implémentation**
d'un projet **général**, à la manière d'une classe qui implémente une interface : le
projet général définit des **procédures, templates, conventions et assets réutilisables**,
le projet implémentation les **applique** à un contexte précis (un client, une instance).

La relation est **plusieurs-à-plusieurs** : un projet peut implémenter **plusieurs**
projets généraux à la fois (ex: une instance Dolibarr cliente implémente *à la fois*
`iprospective/infrastructure` **et** le projet produit Dolibarr général), et un projet
général peut être implémenté par plusieurs enfants. Les deux champs sont donc des **listes**.

| Champ | Sens | Côté |
|---|---|---|
| `implements: [<entité>/<projet>, ...]` | Liste des projets généraux que ce projet implémente | déclaré côté **implémentation** (ex: `abatik/infra` → `[iprospective/infrastructure]`) |
| `implemented_by: [<entité>/<projet>, ...]` | Liste des projets qui implémentent celui-ci | déclaré côté **général** (ex: `iprospective/infrastructure` liste ses projets infra clients) |

Comme `used_by_clients`/`provided_by`, ces deux champs sont **redondants par
construction** (lecture dans les deux sens) ; la cohérence est validée par `pm-doctor.py`
(à venir). Source de vérité = le **frontmatter** `project/overview.md`, pas
l'arborescence. Le chemin canonique reste `paths.project`. Listes vides = `[]`.

**Ne pas confondre avec `provided_by`** : `provided_by` modélise un **livrable**
(un projet — typiquement `product` — dont *le résultat* est consommé par plusieurs
clients) ; `implements` modélise une relation **interface ↔ implémentation** (le projet
enfant *réapplique les procédures/outils* du général à son contexte). Les deux peuvent
coexister sur un même projet.

**Cas d'usage canoniques :**
- **Projets infra client** → implémentent `iprospective/infrastructure`
  (`implements: iprospective/infrastructure`). Le projet général centralise l'outillage
  de supervision, les recettes réseau/stockage, les runbooks ; chaque infra client les
  applique. Se **cumule** avec la détection « projet infra » (slug/nom `infra` ou aspect
  `hosting`/`infrastructure`) qui, elle, conditionne le ticket `008-infra-analysis`
  (voir « Tâches de bootstrap »).
- **Instances produit client** (ex: une instance **Dolibarr** d'un client) →
  implémentent le projet produit général (`<product>/<projet>`).

**Conséquences opérationnelles :**
- **Où poser l'asset ?** Un asset (script, sonde, template, runbook) **réutilisable
  cross-contexte** se dépose dans le **repo du projet général**, pas dans le repo
  enfant. Exemple vécu : `calyclay/infra` implémente `iprospective/infrastructure` —
  la sonde `probe-mail-stack.sh` et les scripts Sieve, réutilisables pour tous les
  clients, ont été déposés dans le repo **général** alors que le ticket de travail
  (RM1835) vivait dans l'enfant. Critère : **réutilisable par d'autres
  implémentations → général ; spécifique à ce contexte → enfant.**
- **Ticket cross-projet.** Un besoin **générique** découvert chez un client se crée
  comme ticket dans le projet **général** (et non dans l'enfant), relié au ticket
  enfant d'origine via `relates`. Le travail spécifique au client reste dans l'enfant.

**Pas de cascade d'aspects** : comme pour le cross-client, `implements` est
**déclaratif** (découverte de l'outillage commun + procédure de placement des assets) ;
il **ne déclenche aucun héritage** de frontmatter ni d'aspects. La cascade reste
mono-client (un projet n'hérite que de son `client:`).

### Aspects — cahier des charges dynamique

Le **cahier des charges** d'un projet est éclaté en plusieurs fichiers (aspects).
Cette approche évite le fichier monolithique illisible et permet d'enrichir
progressivement la connaissance du périmètre. **Deux emplacements** depuis la
privsep (RM2043), selon le discriminant *« a un filet de réconciliation, ou pas »* :

- **`project/`** — aspects **canoniques** consommés par l'outillage : `overview.md`
  (obligatoire, frontmatter + index) et `environments.md`. Couche `mathieu-pm`
  **stricte**, mutation **via `mmi-pm` uniquement**, **hors** wiki-sync.
- **`docs/`** — aspects **libres** (roadmap, data-model, orchestrator, specs, CDC…) :
  **wiki-syncés** (fold-back / merge 3-way) donc sûrs à éditer en direct ;
  group-writable `mathieu`. C'est `docs/` que `pm-wiki-sync` scrute.

**Règles :**
- `overview.md` est **obligatoire** — il porte le frontmatter et un index des aspects
- Tout autre aspect est **optionnel** ; un aspect **libre** se range dans **`docs/`**
  (un `*.md` libre laissé dans `project/` est signalé en erreur par `pm-doctor`)
- L'agent qui charge le contexte lit **tous** les fichiers de `project/` **et** `docs/`
- Les templates d'aspects sont dans `templates/aspects/{domaine}/{aspect}.md`

**Cascade des aspects :**
Un aspect peut exister au niveau client ET au niveau projet. L'agent lit les deux.
Le projet précise/surcharge le client sur les points en contradiction.

Exemple :
- `{entity_client_dir}/hosting.md` : "Tous nos sites sont hébergés chez OVH par défaut"
- `{docs_dir}/hosting.md` : "Ce projet est sur AWS pour des raisons spécifiques"
→ Pour ce projet, l'agent applique AWS (override).

> 📂 **Module `project-creation` — quand lire ceci :** je crée un projet PM↔Redmine · bootstrap · memberships · flux de création de tâches.
> **Outils :** `pm-project-new`, `pm-project-bootstrap` · **Préchargé par :** —.

### Création d'un projet PM ↔ Redmine

À la création d'un nouveau projet PM, le flow doit garantir un mapping **1 ↔ 1** entre
projet PM et projet Redmine. Étapes (à automatiser dans `pm project init`) :

1. **Lister** les projets Redmine accessibles via l'API (`GET /projects.json`)
2. **Vérifier l'existence** d'un projet Redmine avec un identifier candidat
3. **Vérifier l'unicité** d'usage côté PM : itérer `cfg.iter_projects()` (ou
   `grep -r 'redmine.project_id:' "$(cfg.path("entities_dir"))"`) pour s'assurer
   qu'aucun autre projet PM ne référence déjà cet identifier
4. **Trois cas** :
   - Identifier candidat dispo côté Redmine ET non utilisé côté PM → proposer de
     **créer** le projet Redmine (`POST /projects.json`)
   - Identifier existant côté Redmine ET non utilisé côté PM → proposer de **réutiliser**
   - Identifier existant côté Redmine ET déjà utilisé côté PM → bloquer + indiquer le
     projet PM qui l'utilise déjà, demander un autre slug

Le mapping inverse (Redmine identifier → projet PM) doit toujours être unique. Si un
même projet Redmine doit servir plusieurs projets MD, c'est probablement une erreur de
modélisation côté PM (probablement deux projets distincts à créer).

**Memberships par défaut sur un nouveau projet Redmine** (instance iprospective —
`tasks.iprospective.fr`) :

À la création d'un projet Redmine via API (`POST /projects.json`), ajouter
systématiquement ces trois memberships via `POST /projects/<id>/memberships.json` :

| Groupe Redmine | id | Rôle | role_id |
|---|---|---|---|
| `Admin` | 49 | `Manager` | 3 |
| `iProspective` | 70 | `Intervenant` | 7 |
| `Agents IA` | 73 | `Intervenant` | 7 |

Justification :
- `Admin` en Manager garantit que tu (Mathieu) gardes les pleins droits sur le projet,
  sans dépendre d'une appartenance individuelle
- `iProspective` en Intervenant permet aux comptes de l'équipe (humains + agents :
  `claude-chefproj-1`, `karl@`, etc.) de voir et collaborer sur le projet sans devoir
  les ajouter un par un à chaque projet
- `Agents IA` en Intervenant donne aux **agents IA** (karl & co) l'accès au projet —
  sans ce groupe, un nouveau projet n'est pas accessible aux workers IA (RM1977).
  Rôle universel sur l'instance (`Développeur` est ajouté en plus sur les projets dev).

**Branches protégées, dès la création (RM2057).** Une fois le dépôt `-core` publié —
donc dès que sa branche de prod existe —, `pm-project-new` applique `pm-protect` au
dépôt créé, et aux dépôts de code du workspace (`repos/*.git`) qui portent déjà un
remote de forge. Chaque dépôt reçoit la politique de sa nature : `pm-protect` distingue
core et code tout seul, on ne la force pas. **Jamais bloquant** : un échec (droits,
token, forge tierce) s'annonce avec sa commande de rattrapage, et le projet reste créé.
La raison d'être du câblage : posée plus tard, la protection arrive après les premiers
pushes directs — et un dépôt neuf hérite d'un défaut GitLab qui *ressemble* à une
protection conforme sans en être une (cf. `git-mep` § Enforcement).

`pm-project-new.py` (skill `mmi-pm-project-new`) automatise ces trois ajouts à la
création du projet Redmine ; en intervention manuelle, via l'UI Redmine → Settings → Members → Add.

Payload API pour automation :
```bash
# Admin (group_id=49) en Manager (role_id=3)
curl -X POST -H "Content-Type: application/json" -H "X-Redmine-API-Key: $REDMINE_API_KEY" \
  -d '{"membership":{"user_id":49,"role_ids":[3]}}' \
  "$REDMINE_URL/projects/<project_id>/memberships.json"
# iProspective (group_id=70) en Intervenant (role_id=7)
curl -X POST -H "Content-Type: application/json" -H "X-Redmine-API-Key: $REDMINE_API_KEY" \
  -d '{"membership":{"user_id":70,"role_ids":[7]}}' \
  "$REDMINE_URL/projects/<project_id>/memberships.json"
# Agents IA (group_id=73) en Intervenant (role_id=7)
curl -X POST -H "Content-Type: application/json" -H "X-Redmine-API-Key: $REDMINE_API_KEY" \
  -d '{"membership":{"user_id":73,"role_ids":[7]}}' \
  "$REDMINE_URL/projects/<project_id>/memberships.json"
```

### Tâches de bootstrap (`templates/bootstrap-tasks/`)

À la création d'un projet PM, certaines tâches **récurrentes de setup** doivent être
créées pour ne pas oublier les fondations : Vaultwarden, repos git, environnements,
stack, etc. Ces tâches viennent de templates dans `templates/bootstrap-tasks/`.

**Templates standards** (présents dans `templates/bootstrap-tasks/`) :

| ID | Titre | Coché par défaut |
|---|---|---|
| `001-secrets-vaultwarden` | Setup des items de vault + remplir `secrets_source` des envs | ✅ |
| `002-git-repos` | Configurer remote git du workspace, premier push | ✅ |
| `003-environnements` | Documenter envs (dev/test/staging/prod) dans `environments.md` | ✅ |
| `004-stack` | Rédiger `project/stack.md` (langages, framework, dépendances) | ☐ |
| `005-deployment` | Rédiger `project/deployment.md` (CI/CD, rollback) | ☐ |
| `006-testing` | Rédiger `project/testing.md` (stratégie de tests) | ☐ |
| `007-monitoring` | Rédiger `project/monitoring.md` (logs, métriques, alertes) | ☐ |
| `008-infra-analysis` | Analyse de l'infra : inventaire, état, risques (`docs/infrastructure.md`) | ✅ *(projets infra uniquement)* |

> **Projets infra → ticket d'analyse par défaut (v1.30.0).** Tout projet de nature
> **infrastructure** (slug/nom « infra », ou aspect `hosting`/`infrastructure` — qui
> gère des serveurs/hyperviseurs/réseau/stockage plutôt qu'une seule application) doit
> par défaut porter un **ticket d'analyse de l'infra** : état des lieux matériel,
> stockage (disques + SMART, pools/RAID), charges hébergées, monitoring, et une section
> **anomalies** d'où découle **un ticket dédié par anomalie significative**. C'est le
> rôle du template `008-infra-analysis`, proposé **coché** sur ces projets et non
> applicable aux projets purement applicatifs. Le livrable est un document vivant
> (`docs/infrastructure.md` dans le workspace, ou aspect `project/hosting.md`), mis à
> jour à chaque intervention notable.

**Flow d'instanciation** (via `scripts/pm-project-bootstrap.py`) :

1. Détecter les templates **applicables** au projet (état du frontmatter overview,
   présence des aspects, etc.)
2. **Proposer** la liste à l'humain (interactif) — les 3 premiers cochés par défaut,
   les autres non
3. L'humain peut **décocher** ou **cocher** des templates supplémentaires
4. L'humain peut **bypasser** complètement (option `--yes`) ou skip un template
   spécifique (champ frontmatter `bootstrap.skip[]`)
5. Pour chaque template retenu :
   - Créer un ticket Redmine dans `redmine.project_id` du projet
   - Instancier `tasks/RM<id>_<slug>.md` depuis le template (frontmatter rempli)
   - Initialiser le `.log.md`

**Frontmatter `project/overview.md` enrichi pour suivre le bootstrap :**

```yaml
bootstrap:
  skip: []          # IDs de templates explicitement skippés (jamais proposés)
  done: []          # IDs de templates déjà appliqués (= tâche créée)
```

Si un template est dans `done[]`, il n'est plus reproposé (même si le critère de
détection le rend applicable). Si dans `skip[]`, idem. Le flow d'instanciation
remplit `done[]` automatiquement.

**Convention `default_checked` dans les templates :**

Chaque template porte un champ frontmatter `default_checked: true|false` qui
détermine s'il est coché par défaut dans le picker interactif.

### Flux de création de tâches (v1.5.0)

Deux flux supportés :

**a) Création depuis Redmine** (workflow humain ou agent)
1. Un humain (ou un agent) crée le ticket dans Redmine et l'assigne à un agent IA
2. L'orchestrateur détecte l'assignation, génère `paths.task_file` (résolu via
   `pm.config.yml` à partir de l'entité et du projet)
3. Le worker assigné prend la tâche en charge

**b) Création depuis CLI dans le workspace projet** (`pm-task-add.py` / skill `mmi-pm-task-add`)
1. Depuis le workspace de code, l'utilisateur lance `pm task create --type ... --title "..."`
2. Le script crée le ticket Redmine, récupère l'ID
3. Génère le fichier MD dans `.mmi-pm/tasks/RM{id}_*.md` (le symlink pointe vers
   `paths.project`)
4. Commit + push automatique

Le sens inverse pur (MD → Redmine sans ticket préexistant) n'est pas implémenté en
v1.5 — voir [PISTES.md](../PISTES.md).

> 📂 **Module `status-workflow` — quand lire ceci :** je change un statut · je prends une tâche · fin de dev/routing test · un ticket me revient · machine d'états · phase d'étude.
> **Outils :** `pm-task-status-update`, `redmine-fetch-updates` · **Préchargé par :** worker-dev, worker-analyst, orchestrateur.

## Passe agent-testeur indépendante (`requires_agent_test`)

À la fin d'un dev (`en_cours` terminé), le workflow canonique passe par `a_tester_dev`
(test par un **agent/humain testeur ≠ le dev**) avant `a_tester_demandeur`. Cette passe
n'est pas toujours nécessaire (artillerie lourde) — un champ par tâche la **conditionne** :

- **Champ tâche** `requires_agent_test` : `default` (défaut) | `oui` | `non` | `demander`.
- **Défaut projet** : `defaults.requires_agent_test` dans la config projet (`overview.md`).
  Si absent → **défaut système : `non`**.
- **Côté Redmine** : CF **27** « AI Test par agent » (énumération `Oui`/`Non`/`Demander`,
  value ids 39/40/41 ; cf. `redmine.reference.yml :: agent_test_values`). **Non
  sélectionné = `default`** (hérite). Le frontmatter MD fait foi pour l'agent ;
  `pm-task-sync` peut le rafraîchir depuis le CF.

**Résolution + routing** en fin de dev (`requires_agent_test` tâche → si `default`, défaut
projet → si absent, `non`) :

| Valeur résolue | Transition depuis `en_cours` |
|---|---|
| `oui` | → `a_tester_dev` (passe agent-testeur indépendante, attribué à un testeur ≠ dev) |
| `non` | → `a_tester_demandeur` (**bypass**, attribué au demandeur) |
| `demander` | l'agent **demande au demandeur** quelle voie prendre, puis applique |

Un agent en mode non interactif qui tombe sur `demander` (ou ne peut pas résoudre) **reste
en `en_cours`** et le signale plutôt que de trancher seul.

## Machine d'états

```
[a_etudier_chiffrer]
        │ estimation lancée
        ▼
[etude_chiffrage_en_cours]
        │ étude/CDC + chiffrage finis      │ abandonné / hors périmètre
        ▼                                  ▼
[etude_chiffrage_a_valider] (→ demandeur)  [ferme]
        │ validé par le demandeur   ▲ retour demandeur (ajustements)
        │                           └──────────────┐
        ▼                                          │
   [a_faire]                          [etude_chiffrage_en_cours]
        │ démarrage (+ création branche <RMid>-<desc>)
        ▼
   [en_cours] ◄────────────────────────────────────┐
        │ dev terminé                              │
        ▼                                          │
[a_tester_dev] ──── problèmes ───► [a_corriger] ───┤ corrections faites
        │ test dev OK                              │
        ▼                                          │
[a_tester_demandeur] ── rejet ─────────────────────┤  (env DEV : le demandeur
        │ validé par le demandeur sur DEV          │   valide sur l'env de dev)
        │ (MR branche→dev, CF GIT PR, merge)       │
        ▼                                          │
[a_tester_preprod] ── régression préprod ──────────┤  (env PRÉPROD : déploiement
        │ recette préprod OK                       │   préprod qui suit dev, recette)
        ▼                                          │
    [a_mep]                                        │  (validé + en file de MEP —
        │ MR préprod→prod + pull prod              │   PAS encore déployé)
        │ (2 branches : MR dev→prod)               │
        ▼                                          │
    [en_mep] ──── régression prod ─────────────────┘  (EN PROD : déployé, dernière
        │ vérif prod OK                                vérif avant fermeture)
        ▼
    [ferme]

[en_pause]  ⇄  depuis/vers tout état actif (blocage tiers ; reprend à l'état précédent)
[a_tester_demandeur] ──► [ferme]  (ticket sans code à déployer ; close_reason: resolu)
[a_tester_demandeur] ──► [a_mep]  (bypass préprod : projet SANS env préprod → dev→prod direct)
[en_cours] ──► [a_tester_demandeur]  (bypass passe agent-testeur : requires_agent_test=non ; cf. § dédiée)
```

> **⚙ Refonte RM2893 (en cours de livraison — 2026-08-31).** Le tronçon aval a été
> redéfini pour lever une confusion : le statut ne disait pas *où est le code*. Nouvelle
> sémantique par environnement :
>
> | Statut | Env | Sens |
> |---|---|---|
> | `a_tester_demandeur` | **dev** | le demandeur valide sur l'env de dev |
> | `a_tester_preprod` (**nouveau, optionnel**) | **préprod** | merge dev + déploiement préprod, recette ; **sauté** si le projet n'a pas d'env préprod (→ `a_tester_demandeur` va direct à `a_mep`) |
> | `a_mep` | — | validé, en file de MEP — **pas encore déployé** |
> | `en_mep` (**redéfini**) | **prod** | déployé en prod, **dernière vérif avant fermeture** |
>
> Avant : `en_mep` = « tester en préprod » et le déploiement prod se faisait *en sortant*
> d'`en_mep`. Désormais le déploiement prod se fait **en entrant** dans `en_mep`, qui
> devient l'état « en prod, en attente de fermeture ». Motivation : le flux *deploy-first*
> (déployer puis faire valider) n'avait aucun statut exprimant « en prod + à fermer »
> (constat session 2026-08-28 : RM2575/2576/2885/2886 tous « en prod » mais posés en
> `a_tester_demandeur`). Mapping Redmine, attribution et routing outillage mis à jour dans
> le même lot (cf. § Mapping et `pm-task-status-update`). Les deux statuts Redmine existent
> déjà : `a_tester_preprod` = id **20** « MEP/Tester en preprod » ; `en_mep` = id **22**
> « MEP/Vérifier en prod » (aucune création/renommage).

Règle : **toute transition vers `ferme` requiert un `close_reason`.**
Le workflow complet (branches, envs, MEP) est décrit en § *Cycle de
développement → test → mise en production*.

### Flux court micro-tâches — v1.61.0 (RM2369, CDC RM2316 § S8)

**Critère** : `estimate.time_minutes ≤ 30` **et** pas de livrable code (audit
éclair, doc courte, correction de données, assistance). Constat d'audit
(RM2275) : sur ces tickets la cérémonie atteignait 40–59 % du coût.

**Séquence** — mêmes statuts, mêmes notes (templatées § traceability), zéro
infrastructure inutile :

1. `pm-task-take <id> --no-branch` — en_cours + assignation, PAS de branche ni
   d'env de session ;
2. travail + entrée `.log.md` (le sémantique reste obligatoire) ;
3. `pm-task-deliver <id> --summary -` — critères/protocole/routage inchangés.

Travail déjà fait au moment de la création → `pm-task-add --retro` (le ticket
traverse la machine d'états en un appel). Un micro-ticket qui grossit en cours
de route (code nécessaire) repasse au flux standard : `pm-task-take <id>`
(idempotent) crée branche + env à ce moment-là.

### Tâche

- `redmine_id: <int>` est **obligatoire** dans le frontmatter
- Le nom de fichier `RM{id}_{titre}.md` **doit correspondre** à `redmine_id`
  (cohérence vérifiée par le validateur)
- Pas de tâche MD sans ticket Redmine préexistant

### Projet

- `redmine.project_id: <slug>` est **obligatoire** dans `project/overview.md`
- `redmine.subprojects: [slug, slug, ...]` est optionnel — liste les sous-projets
  Redmine rattachés (utile quand plusieurs sous-projets concernent ce même projet MD)

### Synchronisation des statuts MD ↔ Redmine (obligatoire)

**Tout changement de `status` dans le frontmatter d'une tâche doit être répercuté
sur le ticket Redmine correspondant**, dans le même cycle de travail.

L'agent (ou l'orchestrateur) qui modifie le `status` MD doit :
1. Mettre à jour le frontmatter (`status`, `status_history`, `updated`)
2. Appender l'événement dans `.log.md`
3. Poster une note Redmine + changer le `status_id` correspondant
   (typiquement via `scripts/redmine-post-note.py --norms-status <statut>`)

**Demandeur effectif = `author_id` natif Redmine** (cf. RM1735) :

Le ticket porte son demandeur via le champ standard `author_id`. À la création
par `pm-task-add.py`, un PUT immédiat ajuste `author_id` :
- **Par défaut** → Manager IA (`pm.config.yml :: ia.default_manager.redmine_id`)
- **Avec `--initiator-agent`** → karl (id=79) : audits autonomes, bootstrap
  automatique, tâches initiées par un agent

Le CF `Demandeur` (id=12) est **déprécié** (cf. RM1739 pour la suppression
définitive sur l'instance). Plus aucun script ne le consulte.

**Règle d'attribution Redmine** :
- Passage en `etude_chiffrage_a_valider` → ré-attribuer au **demandeur** (author) :
  l'étude / CDC / chiffrage sont finis et soumis à sa validation. **Même résolveur
  que `a_tester_demandeur`** (author ≠ karl → author ; author == karl → Manager IA).
  Appliqué automatiquement par `pm-task-status-update.py`.
- Passage en `a_tester_dev` → ré-attribuer à un **testeur ≠ le dev** (agent ou
  humain), pour un test indépendant en env `test`. Manuel via `--assign-to <id>`
  pour l'instant ; l'orchestrateur routera vers un worker-test quand il sera en place.
- Passage en `a_tester_demandeur` → ré-attribuer au **demandeur** (author).
  Résolveur appliqué par `pm-task-status-update.py` :
  1. `author == karl` (cas légitime --initiator-agent) → **Manager IA**
  2. `author ≠ karl` avec email accessible → cet `author`
  3. fallback (email inaccessible) → Manager IA
- Passage en `a_tester_preprod` (RM2893, **optionnel**) → ré-attribuer au **responsable
  recette préprod** (par défaut le **demandeur** — même résolveur que `a_tester_demandeur` ;
  configurable par projet). Étape sautée si le projet n'a pas d'env préprod
  (`a_tester_demandeur` → `a_mep` direct).
- Passage en `a_mep` → ré-attribuer au **responsable MEP / intégration** (par défaut
  Manager IA ou orchestrateur ; configurable par projet).
- Passage en `en_mep` (RM2893, **redéfini = en prod, dernière vérif avant fermeture**) →
  ré-attribuer au **demandeur** (author) pour la vérification finale en prod avant clôture
  (même résolveur que `a_tester_demandeur`). ⚠ Ancienne sémantique « testeur préprod »
  dépréciée.
- Passage en `a_corriger` → ré-attribuer au **worker** précédent (manuellement pour
  l'instant via `--assign-to <id>`, automatisé quand l'orchestrateur sera en place).
- Passage en `en_pause` → **conserver** l'attribution courante (la tâche reste
  possédée, juste sortie des files actives).
- Passage en `ferme` → conserver l'attribution courante.

> Note : `a_tester_verifier` (≤ v1.18.0) est **déprécié**, remplacé par le couple
> `a_tester_dev` / `a_tester_demandeur`. Les scripts l'acceptent encore en lecture
> et le normalisent vers `a_tester_demandeur` (rétrocompat).

**Manager IA** (cf. RM1734) : humain qui supervise les agents (karl + futurs),
reçoit la notif mail à chaque livraison, se voit assigner les tickets
`a_tester_demandeur` quand l'auteur est karl. Configuré dans `pm.config.yml` :

```yaml
ia:
  default_manager:
    redmine_id: 5
    email: mathieu@iprospective.fr
    name: Mathieu Moulin
```

V2 prévue : cascade par projet (`ia.managers:` par `paths.project`) et/ou
champ `ia_manager:` dans le frontmatter de `project/overview.md`.

### Prise en charge d'une tâche : `en_cours` ⇒ auto-assignation (obligatoire) — v1.12.0

**Règle** : un agent qui commence à travailler sur une tâche doit, dans le **même
mouvement** :

1. Passer le `status` de la tâche à `en_cours` (côté Redmine + frontmatter MD + log)
2. **S'assigner le ticket Redmine** (champ `assigned_to`) si ce n'est pas déjà le cas

Les deux opérations sont **indissociables**. Une tâche `en_cours` sans
`assigned_to` cohérent est un état invalide : `en_cours` signifie « un agent
nommément identifié est en train de faire le travail maintenant ». Pas
d'`en_cours` flottant.

Cette règle vaut **même hors orchestrateur** (mode interactif Claude Code) : si
un humain demande à l'agent de bosser sur RM1234 et que le ticket n'est ni à
`en_cours` ni assigné à l'agent, l'agent fait lui-même les deux opérations avant
de démarrer le travail effectif.

**Symétrie avec la `Vérification initiale` de [worker-common.md](../agents/worker-common.md)** :
ce qu'un worker orchestré vérifie passivement (status + assigné à soi), un agent
en mode interactif l'établit activement au démarrage.

**Implémentation** : `pm-task-status-update.py` **couple** status + assignation —
quand la cible est `en_cours`, il auto-assigne au user Redmine de l'agent courant
(résolu via `pm.config.yml :: agents.<id>.redmine_id`, défaut karl=79). Aucun PUT
manuel à faire ; `--no-assign` pour outrepasser.

**Mapping NORMS → Redmine (instance iprospective)** — après consolidation RM1742 :

Statut Redmine (un seul terminal `Fermé`) :

| NORMS | Redmine | id |
|---|---|---|
| `nouveau` | Nouveau | 1 |
| `a_etudier_chiffrer` | A étudier / Qualifier | 8 |
| `etude_chiffrage_en_cours` | Etude/CDC en cours | 14 |
| `etude_chiffrage_a_valider` | Etude/CDC à valider | 21 |
| `a_faire` | A Faire | 12 |
| `en_cours` | En cours | 2 |
| `a_tester_dev` | A tester/vérifier dev | 19 |
| `a_tester_demandeur` | A tester/vérifier demandeur | 9 |
| `a_tester_preprod` (RM2893) | MEP/Tester en preprod | 20 |
| `a_mep` | Résolu/Validé/A MEP | 3 |
| `en_mep` (RM2893) | MEP/Vérifier en prod | 22 |
| `en_pause` | Attente retour / en pause | 13 |
| `a_corriger` | A corriger/finir | 11 |
| `ferme` (toutes raisons) | Fermé | **18** |

> **RM2893 — migration du mapping (2026-08-31).** Les deux statuts Redmine existaient déjà
> et leurs libellés collent : **aucune création ni renommage**. Seul changement d'id :
> `en_mep` passe de **20 → 22** (« MEP/Vérifier en prod »), et le statut **20**
> (« MEP/Tester en preprod ») devient `a_tester_preprod`. Les tickets déjà au statut 20
> (préprod) sont donc réinterprétés `en_mep`→`a_tester_preprod` — sémantiquement exact,
> ils restent au même statut Redmine ; leur frontmatter MD se réaligne au prochain
> `pm-task-sync`. ⚠ Vérifier que les transitions de workflow Redmine (par rôle/tracker)
> autorisent bien l'entrée en 20 depuis `a_tester_demandeur` et en 22 depuis `a_mep`
> (sinon le PUT échoue silencieusement — cf. `knowledge/redmine/gotchas.md`).

`a_tester_verifier` (déprécié) → lu comme `a_tester_demandeur` (id 9).
`a_mep` (Résolu/Validé/A MEP, id 3) est un statut **non terminal** (validé par le
demandeur, mergé dans l'intégration, en file de MEP) — à ne pas confondre avec
`ferme`.

`nouveau` (Nouveau, id 1) est le **statut d'entrée** : `pm-task-add.py` crée par
défaut un ticket en `nouveau` (ticket déposé, non encore trié/engagé), avec
`author_id` posé mais **sans `assigned_to`** (pas encore pris en charge). Le tri
vers `a_faire` / `a_etudier_chiffrer` / `en_cours` se fait ensuite (manuellement
ou à la création via `pm-task-add.py --status <statut>`, qui crée en `nouveau`
puis transitionne via `pm-task-status-update.py` pour bénéficier du couplage
NORMS — assignation, note, `status_history`). Un ticket reste légitimement en
`nouveau` tant qu'il n'a pas été engagé ; ce n'est pas un état invalide.

Raison de fermeture (CF `Raison Fermé`, id=11, format enumeration) — valeurs :

| NORMS `close_reason` | CF Raison Fermé | value_id |
|---|---|---|
| `resolu` | Résolu | 10 |
| `wont_fix` / `hors_perimetre` | Rejeté | 11 |
| `abandonne` | Abandonné | 12 |
| `doublon` | Déjà existant | 13 |
| `invalide` | Pas un bug / rien à faire | 14 |

Note : les anciens statuts terminaux `Résolu/Fermé` (5), `Rejeté` (6),
`Pas un bug / Déjà existant` (7), `Abandonné` (10) sont **dépréciés** —
à désactiver/supprimer en UI Redmine. Attention à ne pas les confondre avec le
nouveau `Résolu/Validé/A MEP` (id 3, `a_mep`), qui est **non terminal**.

## Lien Redmine ↔ MD (obligatoire)

Toute entité du système (tâche, projet) **doit** être reliée à son équivalent Redmine.
Cette règle est vérifiée par le validateur.

> 📂 **Module `status-workflow-pratique` — quand lire ceci :** je cherche la transition exacte permise depuis un statut · je qualifie/chiffre en phase d'étude · une transition m'est refusée alors que je ne suis pas l'assigné · un ticket revient avec des notes du demandeur.
> **Outils :** `pm-task-status-update --list-next`, `redmine-fetch-updates` · **Préchargé par :** *(personne — ouvert à la demande)*.

# Statuts — table des transitions et cas particuliers

Détaché de `status-workflow.md` par RM2582. La table des transitions est une
**référence** : le KERNEL impose déjà de la demander à l'outil
(`pm-task-status-update --list-next`) plutôt que de la deviner — la porter en
permanence dans le contexte de tous les workers ne servait à rien. Les règles
obligatoires (machine d'états, synchronisation MD ↔ Redmine, auto-assignation à
la prise) sont restées dans `status-workflow.md`.

### Transitions valides

| De | Vers | Condition |
|---|---|---|
| `a_etudier_chiffrer` | `etude_chiffrage_en_cours` | `assigned_to` renseigné |
| `etude_chiffrage_en_cours` | `etude_chiffrage_a_valider` | CDC + `estimate.*` complets → soumis au demandeur (ré-attribution `author`) |
| `etude_chiffrage_a_valider` | `a_faire` | validé par le demandeur → prêt à coder |
| `etude_chiffrage_a_valider` | `etude_chiffrage_en_cours` | retour demandeur (ajustements étude/chiffrage) |
| `etude_chiffrage_{en_cours,a_valider}` | `ferme` | `close_reason` requis |
| `a_faire` | `en_cours` | création branche `<RMid>-<desc>` + CF `GIT Branche` |
| `en_cours` | `a_tester_dev` | dev terminé + `requires_agent_test` résolu à `oui` |
| `en_cours` | `a_tester_demandeur` | dev terminé + `requires_agent_test` résolu à `non` (bypass passe agent-testeur) ; `demander` → demandeur tranche |
| `en_cours` | `a_etudier_chiffrer` | périmètre modifié |
| `a_tester_dev` | `a_tester_demandeur` | test dev OK |
| `a_tester_dev` | `a_corriger` | problèmes (note dans journal) |
| `a_tester_demandeur` | `a_tester_preprod` | *(RM2893, si préprod)* validé sur **dev** : MR branche→`integration_branch` (CF `GIT PR`) mergée + déploiement préprod |
| `a_tester_demandeur` | `a_mep` | *(projet SANS préprod)* validé : MR branche→`integration_branch` (CF `GIT PR`) puis mergée |
| `a_tester_demandeur` | `a_corriger` | rejet (note dans journal) |
| `a_tester_demandeur` | `ferme` | ticket sans code à déployer — `close_reason: resolu` |
| `a_tester_preprod` | `a_mep` | *(RM2893)* recette **préprod** OK : en file de MEP |
| `a_tester_preprod` | `a_corriger` | régression préprod (note dans journal) |
| `a_mep` | `en_mep` | déployé en **PROD** : **3 branches** MR `preprod`→`prod_branch` / **2 branches** MR `dev`→`prod_branch` + pull prod |
| `en_mep` | `ferme` | *(RM2893 : `en_mep` = en prod)* vérif **prod** OK — `close_reason: resolu` |
| `en_mep` | `a_corriger` | régression **prod** (note dans journal) |
| `a_corriger` | `en_cours` | — |
| `* (tout état actif)` | `en_pause` | blocage tiers ; reprend à l'état précédent au déblocage |
| `* (tout état)` | `ferme` | `close_reason` requis |
| `ferme` | `a_faire` | **réouverture** (RM2285) : note obligatoire motivant la réouverture ; `close_reason` purgé |

**Réouverture d'un ticket fermé (RM2285).** Un ticket `ferme` peut être rouvert
**uniquement vers `a_faire`** (retour au backlog — la reprise suit ensuite le flow
normal `a_faire → en_cours → …`, jamais de saut direct en réalisation). Conditions,
imposées par `pm-task-status-update` :
- **note obligatoire** motivant la réouverture (elle part en note Redmine et au journal) ;
- `close_reason` est **purgé** (`null`) — un ticket rouvert n'est plus « résolu » ;
- `status_history` **conserve le cycle précédent** (append-only) : l'historique
  fermeture(s)/réouverture(s) reste lisible.

Rouvrir n'est PAS le chemin pour « corriger une livraison qui régresse » — ça, c'est
`a_corriger` avant fermeture. On rouvre quand un ticket **déjà validé et clos** doit
reprendre du service (nouveau périmètre sur le même sujet → préférer un **nouveau
ticket lié** `relates` ; même périmètre non terminé en réalité → réouverture).

**Livraison en vérification — protocole de test + URL de test (RM2229).** Le
**protocole de test** (CF Redmine « Protocole de test », miroir frontmatter
`test_protocol`) se rédige **au fil de l'eau**, à chaque étape d'avancement du dev —
pas rétroactivement à la livraison : `pm-task-protocol <id> --set -/--append -`.
Au passage en `a_tester_dev`/`a_tester_demandeur`/`a_mep` : protocole non vide
(le garde-fou de `pm-task-status-update` avertit) et **`test_url` renseigné** —
automatique si l'env de session existe (`pm-env-session create` écrit frontmatter
+ CF « Environnement de test » ; le teardown les vide), sinon manuel. Le testeur
doit savoir **quoi tester et où** sans relire tout le ticket (fiche de revue cockpit).

**Précondition de fermeture — sous-tâches.** Un ticket qui possède des
**sous-tâches** ne peut passer en `ferme` que lorsque **toutes ses sous-tâches sont
elles-mêmes `ferme`**. C'est imposé côté Redmine (la transition du parent est
**refusée** tant qu'un enfant reste ouvert) — corollaire de la règle d'orchestration
« un parent passe en `ferme` uniquement quand tous ses enfants directs sont `ferme` »
(module `collaboration`, § *Propagation de complétion*).

**Précondition de fermeture — relations bloquantes.** De même, un ticket **bloqué par**
une relation `blocks` / `precedes` (= NORMS `depends_on`) ne peut être fermé tant que le
ticket **source** reste ouvert — refus tout aussi **silencieux** que pour les sous-tâches.
Ce n'est **ni** un problème de droit, **ni** de workflow, **ni** de tracker. (Vécu sur
RM1813, bloqué par #1816 / #1814 / #1848 encore ouverts.)

**Outil de diagnostic — `pm-task-blockers.py <id>` (réflexe).** Dès qu'une transition vers
`ferme` (ou tout statut) est **refusée silencieusement**, lancer
`scripts/pm-task-blockers.py <id>` : il liste en un coup les **relations bloquantes
ouvertes** (blocks/precedes) ET les **sous-tâches ouvertes**, et dit **quoi clôturer
d'abord** (`--json` pour l'outillage). À préférer au diagnostic manuel ci-dessous.

> **Comment ça se manifeste (piège diagnostique).** Le refus est **silencieux** : le
> `PUT` renvoie 204, la note éventuelle est bien postée, mais le `status_id` est
> **ignoré** — le statut reste inchangé. `redmine-post-note` / `pm-task-status-update`
> rapportent alors « *permission 'Edit issues' manquante* », ce qui est une
> **interprétation** (statut inchangé après PUT), **pas la vraie cause**. Ne pas
> conclure à un problème de droits, de rôle ou de tracker (« Evolution » et « Tâche »
> ont les **mêmes** droits). Diagnostic autoritatif :
> `GET /issues/<id>.json?include=allowed_statuses` (si `18 Fermé` est absent → transition
> non permise) puis `?include=children,relations` (un enfant non clos **ou** une relation bloquante ouverte = le blocage ; `pm-task-blockers.py` automatise les deux). Remède :
> fermer/détacher l'enfant d'abord, ou — si le contenu de référence doit rester sur le
> parent — créer une **sous-tâche « cadrage » clôturable** (cf. encadré ci-dessous).

> **Conséquence de modélisation (à anticiper).** Le **contenu** d'un livrable de
> cadrage (CDC, étude, décision d'architecture) peut tout à fait **vivre dans la
> description du parent** quand il sert de **pilote** (référence « north-star » pour les
> enfants) — c'est même souhaitable. Ce qui ne doit pas reposer sur le parent, c'est la
> **clôture** de ce livrable : le parent restant bloqué ouvert tant que ses sous-tâches
> d'implémentation ne sont pas fermées, créer une **sous-tâche dédiée** (« cadrage / CDC »)
> que l'on clôt pour acter l'achèvement de l'étude. Principe : **dissocier le contenu de
> référence (description du parent, pilote) de l'unité clôturable (sous-tâche).** Le parent
> reste un **conteneur** dont la fermeture suit celle de ses enfants.
### Phase d'étude / qualification : audit, analyse & CDC *avant* de coder — v1.25.0

Les deux premiers statuts du workflow ne sont **pas** une simple file d'attente
administrative : ils matérialisent une **phase de travail à part entière**,
réalisée **avant d'écrire la moindre ligne de code**. Aucun ticket non trivial ne
passe directement à `a_faire` / `en_cours` sans être passé par cette phase.

| Statut NORMS | Redmine | Sens |
|---|---|---|
| `a_etudier_chiffrer` | A étudier / Qualifier (8) | Le ticket est entré mais pas encore analysé : **file d'attente de la qualification**. |
| `etude_chiffrage_en_cours` | Etude/CDC en cours (14) | **Phase active** : audit de l'existant, analyse du besoin, rédaction du CDC, découpage, estimation. |
| `etude_chiffrage_a_valider` | Etude/CDC à valider (21) | **Étude finie, soumise au demandeur** : le livrable (CDC + chiffrage) attend sa validation. Ticket ré-attribué au demandeur. |

**Contenu de l'étude** (`etude_chiffrage_en_cours`) :
- **Audit** — lire le code, l'infra, les contraintes ; cartographier l'existant et les pièges.
- **Analyse** — clarifier le besoin réel, les cas limites, les non-objectifs.
- **CDC** — produire / mettre à jour le cahier des charges (aspect projet, cf. § *Aspects*).
  C'est le **livrable** de cette phase pour tout ticket non trivial.
- **Découpage & chiffrage** — sous-tickets éventuels, `estimate.*` complet.

**Fin de l'étude : soumettre au demandeur (obligatoire) — v1.28.0.** Quand l'étude
est terminée (CDC rédigé, `estimate.*` complet), l'agent **ne passe pas directement
à `a_faire`** : il passe le ticket en **`etude_chiffrage_a_valider`**, ce qui le
**ré-attribue au demandeur** (author ; author == karl → Manager IA — même résolveur
que `a_tester_demandeur`). Le demandeur valide le périmètre + le chiffrage avant tout
développement. C'est le pendant amont du `a_tester_demandeur` aval.

**Sorties de phase** :
- `etude_chiffrage_en_cours → etude_chiffrage_a_valider` — étude finie, CDC + `estimate.*` complets → soumis au demandeur (ré-attribution automatique).
- `etude_chiffrage_a_valider → a_faire` — validé par le demandeur → prêt à coder.
- `etude_chiffrage_a_valider → etude_chiffrage_en_cours` — retour du demandeur : ajustements d'étude / de chiffrage demandés.
- `etude_chiffrage_{en_cours,a_valider} → ferme` — abandonné / hors périmètre (`close_reason` requis).

Un ticket de type `audit`, `research` ou `design` peut **rester** dans cette phase
jusqu'à sa fermeture : le livrable *est* l'étude, pas du code. À l'inverse, un ticket
en `en_cours` dont le périmètre change repasse en `a_etudier_chiffrer` (cf. transitions).

**Synchronisation Redmine** : ces trois statuts sont mappés (§ *Mapping NORMS → Redmine*,
ids **8**, **14** et **21**) et pilotés par les skills/scripts habituels — `mmi-pm-task-status-update`
(`pm-task-status-update.py`), `redmine-post-note.py --norms-status`. On ne fixe **jamais**
un statut Redmine « en dur » : on passe toujours par le mapping NORMS.
### Transitions « assignee-only » — v1.31.0

Dans le workflow Redmine, **certaines transitions ne sont autorisées que si le ticket
est assigné au compte API courant** (karl, id 79). C'est notamment le cas des deux
transitions qui *soumettent au demandeur* :

- `etude_chiffrage_en_cours → etude_chiffrage_a_valider` (Redmine **14 → 21**) ;
- `* → a_tester_demandeur` (Redmine → **9**).

Or ces transitions s'accompagnent justement d'une **réattribution au demandeur**. Si
l'on pousse `status_id` **et** `assigned_to_id` (= demandeur) dans le **même PUT** alors
que le compte API n'est pas (encore) l'assigné, Redmine évalue le workflow sur l'assigné
**avant** mise à jour → la transition est **refusée silencieusement** : `HTTP 204` mais
statut inchangé (faux diagnostic « permission *Edit issues* manquante »).

**Règle d'exécution (gérée automatiquement par `redmine-post-note.py`)** : avant un PUT
de statut, si le statut cible n'est pas dans `allowed_statuses` et que le compte API
n'est pas l'assigné courant, **s'auto-assigner d'abord** (PUT préalable) pour débloquer
la transition, **puis** faire le PUT principal (statut + réattribution finale au
demandeur). Conséquence visible : un journal d'assignation supplémentaire (→ karl, puis
→ demandeur). Ne **jamais** contourner en fixant le statut « en dur ». Le mapping inverse
Redmine→NORMS (`pm-task-sync.py`) doit connaître l'id **21** sous peine de laisser le MD
périmé sur `etude_chiffrage_en_cours`.
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
5. Resoumettre via `redmine-post-note.py --norms-status a_tester_demandeur` (qui
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
> 📂 **Module `redmine-sync` — quand lire ceci :** tu introduis ou fais évoluer une **donnée / vue / artefact partagé** entre Redmine et le PM (nouveau champ, nouvelle vue, template d'issue, doc, métrique…) · tu te demandes « où est la source de vérité et comment les deux côtés restent-ils alignés ? ».
> **Outils :** scripts de sync dédiés (`pm-task-status-update`, `pm-task-description-update`, `redmine-template-sync`, `pm-wiki-sync`, `pm-task-metrics-push`…) · **Préchargé par :** —.

## Principe de parité Redmine ↔ PM

**On cherche en permanence à établir (ou à rapprocher) la synchronisation entre les
données Redmine et les données PM — pour qu'humains et agents IA voient toujours le
même état.** Redmine est la **vitrine humaine**, les fichiers MD sont le **plan de
travail des agents**, mais c'est le **même état** vu sous deux angles, pas deux
référentiels concurrents.

Toute donnée qui existe **des deux côtés** (statut, priorité, titre, description /
CDC, done_ratio, liens entre tâches, métriques temps/tokens…) est tenue synchronisée
**dans le même cycle** que sa modification — jamais mise à jour d'un seul côté en
laissant l'autre dériver.

### Objectif directeur, pas perfection imposée

C'est un **objectif directeur**. La parité parfaite n'est pas toujours atteignable
(API partielle, plugin sans REST, latence de fetch…) ; la règle est alors :
**réduire l'écart, jamais l'agrandir sciemment**. Quand un côté ne peut pas être
synchronisé automatiquement, on le documente et on prévoit le rapprochement, plutôt
que d'acter une divergence silencieuse.

### Conséquence pratique — concevoir la sync *avant* la copie

Chaque fois qu'on introduit une donnée ou un artefact partagé, on conçoit **d'abord**
sa synchronisation :

- privilégier une **source canonique unique** dont les autres représentations sont
  des **miroirs générés**, plutôt que plusieurs copies maintenues à la main ;
- si la cible n'a pas d'API (ex. plugin Redmine), écrire l'outil de sync qui pousse
  la source vers la cible de façon **idempotente** (un trou d'outillage = un script
  à créer, cf. tripwire #1) ;
- marquer toute représentation **générée** comme telle (bandeau « ne pas éditer ici »)
  pour ne pas recréer un drift à deux sources.

### Format du livrable — portable et versionné

Avant de se demander *comment* on synchronise une source canonique, il faut se
demander **dans quoi elle vit**. La réponse est invariante :

**Tout livrable documentaire — audit, CDC, spec, roadmap, rapport — est du markdown
dans le repo git du projet.** C'est la source canonique : diffable, revue en MR,
versionnée, lisible par n'importe qui.

**Interdit : un livrable dont la source vit dans un outil propriétaire à un
fournisseur de LLM** (Artifact, canvas, doc hébergé côté vendor…) ou dans tout format
qu'un autre agent, outil ou humain ne peut pas reprendre. Le système PM est
**fédéré et multi-agents** : un livrable qui n'existe que dans le contexte d'un
fournisseur est un livrable perdu dès qu'on change d'agent — et une source hors git,
donc sans diff, sans revue, sans historique.

> **Critère de décision** — *« un autre LLM, demain, sans mon outillage, peut-il
> lire, éditer et versionner ce livrable ? »* Si la réponse est non, le format est
> mauvais, quelle que soit sa qualité de rendu.

Les représentations hébergées (Wiki Redmine, description projet…) restent ce qu'elles
sont partout ailleurs dans ce module : des **miroirs générés** depuis git (via
`pm-wiki-sync`), jamais la source. Le rendu joli est un miroir ; le markdown est le
livrable.

Corollaire pour les agents disposant d'outils de rendu (Artifacts & co) : ils sont
utilisables comme **vue jetable** (prévisualiser, montrer), jamais comme livrable ni
comme source. Le cycle reste : markdown en repo → commit → miroir généré.

### Ce principe est l'ombrelle de tripwires concrets déjà en vigueur

Il ne remplace pas, il **chapeaute** — le détail vit dans les modules dédiés :

- **Statut** (tripwire #4) : tout changement de `status` se répercute Redmine
  (status_id + note) + frontmatter + `.log.md` dans le même cycle. → `status-workflow`.
- **Description vivante** (tripwire #9) : la description Redmine est l'état courant,
  tenue à jour (checklist, done_ratio) ; les notes sont l'historique. → `redmine-hygiene`.
- **Traçabilité** (tripwire #12) : note Redmine + entrée `.log.md` à chaque étape
  significative. → `traceability`.
- **Liens** entre tâches : miroir maintenu des deux côtés. → `task-links`.
- **Métriques** temps/tokens poussées vers les CF Redmine. → `roi-pricing`.
- **Docs / Wiki** : aspects et overviews poussés en Wiki / description projet depuis
  git (source canonique, wiki = miroir). → `pm-wiki-sync`.

### Exemples de référence

- **`redmine-template-sync.py`** — les templates d'issue (plugin
  `redmine_issue_templates`, sans API REST) sont des **miroirs** d'un fichier source
  unique (`templates/redmine/issue-body.md`), poussés via rails runner idempotent.
  On édite la source, on relance, les N templates sont alignés (RM2016).
- **`pm-wiki-sync`** — sens unique git → Wiki, bandeau « généré » sur chaque page.
> 📂 **Module `redmine-hygiene` — quand lire ceci :** le ticket a une checklist · sa description est périmée · son done_ratio évolue.
> **Outils :** `pm-task-description-update` · **Préchargé par :** worker-dev, worker-analyst, worker-design.

### Mise à jour de la description du ticket Redmine (obligatoire) — v1.13.0

La **description** d'un ticket Redmine (le corps principal, distinct des notes
de journal) est un document **vivant** : ce n'est pas un message figé à la
création, mais l'état courant de la demande. L'agent doit la maintenir à jour
chaque fois que son contenu cesse de refléter la réalité.

**Quatre déclencheurs obligent à mettre à jour la description** :

1. **La description contient des informations d'état qui ont changé** — par
   exemple un statut interne décrit en prose (« En attente de validation
   client », « bloqué par X »), une URL d'environnement de test, une version
   cible, une décision provisoire. Si la description affirme quelque chose qui
   n'est plus vrai, elle doit être réécrite, pas seulement contredite dans une
   note.
2. **La description contient une liste de tâches / une checklist** dont l'état
   évolue (cases cochées Markdown `- [ ]` / `- [x]`, sous-objectifs, critères
   d'acceptation, étapes restantes). À chaque progression, l'agent met à jour
   les cases ou items concernés **dans la description elle-même**, pas
   uniquement dans une note. La description sert de tableau de bord ; les notes
   servent à l'historique.
3. **Demande explicite** du demandeur ou d'un autre intervenant (« mets à jour
   la description avec X », « ajoute Y dans la description », reformulation
   demandée du périmètre, etc.).
4. **Modification substantielle de la demande en cours de travail** — quand
   le demandeur change un nom de chemin, un identifiant, une cible, ou
   ajoute/retire un item du périmètre **après** que la description a été
   rédigée. Le re-cadrage doit être répercuté dans la description (pas
   seulement traité dans une note de journal), car la description sert de
   référence pour la vérification finale. Ex : la description liste
   `old/ → erp_old/old/` mais le demandeur demande ensuite `erp_old/dev/` —
   réécrire la description avec `erp_old/dev/`, et accompagner d'une note
   « Description mise à jour suite re-cadrage : `erp_old/old` → `erp_old/dev` ».
   Ne **pas** se contenter d'une note « fix complémentaire » : si quelqu'un
   relit la description plus tard, il doit y voir l'état final, pas
   l'état initial.

**Note de journal accompagnante** : toute mise à jour de description doit être
accompagnée d'une note Redmine résumant **ce qui a changé** et **pourquoi**
(« Description : coché items 3 et 4 de la checklist (livraison faite, doc à
jour) »). Cela préserve la traçabilité — Redmine ne diff pas les descriptions
dans l'UI standard.

**Symétrie avec les notes** :
- **Note** = événement daté, append-only, raconte le « quoi s'est passé ».
- **Description** = état courant, mutable, raconte le « où on en est ».

Une checklist cochée uniquement dans une note (et pas dans la description) est
invisible dès qu'on scrolle ; une décision d'état figée dans la description
initiale et contredite par 12 notes successives est illisible. Les deux médias
sont complémentaires et **les deux doivent être tenus à jour**.

**% réalisé (`done_ratio`) au fil de l'eau** — v1.16.0 : l'agent maintient le
pourcentage de réalisation du ticket (`done_ratio` Redmine ↔ `completion_pct` MD)
**au fur et à mesure**, pas seulement à la clôture. La valeur se dérive :
- du **ratio de cases cochées** de la checklist quand il y en a une
  (`cochées / total`, arrondi) — c'est la règle par défaut ;
- sinon de l'**évaluation de l'agent** (avancement estimé du travail).

Le changement de `done_ratio` étant **journalisé nativement** par Redmine (comme
le statut, cf. v1.15.0), il ne donne **pas** lieu à une note dédiée. Une note
n'accompagne que les changements de **description** (texte/checklist), que Redmine
ne diff pas. Cocher un item de checklist EST une modification de description → note ;
faire passer le `done_ratio` de 50 à 75 → pas de note.

**Implémentation** (état v1.16.0) :
- **`pm-task-description-update.py <rm-id>`** : coche/décoche la checklist
  (`--check 1,2`, `--uncheck 3`, `--check-all`), met à jour `done_ratio`
  (`--done-ratio auto` depuis la checklist, ou un entier), ou remplace toute la
  description (`--set-from-file`). PUT Redmine (`description` + `done_ratio` +
  `notes` si la description a changé) + sync MD (`completion_pct` + checklist du
  corps) + append `.log.md`. C'est le wrapper de référence.
- **`pm-task-status-update.py`** refuse de passer une tâche en `a_tester_demandeur`,
  `a_mep` ou `ferme:resolu` s'il reste des items de checklist **non cochés** dans la
  description (`--allow-unchecked` pour outrepasser si c'est volontaire). Garde-fou
  pour ne pas livrer/clore avec une checklist non tenue à jour.

> 📂 **Module `redmine-reference` — quand lire ceci :** avant une session touchant l'intégration Redmine / périodiquement · ids CF/statuts/activités · filtrage IA.
> **Outils :** `redmine-config-check` · **Préchargé par :** —.

## Résolution projet → Redmine (précise, jamais par slug nu)

**Règle (tripwire #14).** Toute opération Redmine ciblant un projet (sync wiki,
note, description, stats…) résout le projet par référence **non ambiguë** :

- `client/slug` — ex. `matnat/infra` (désambiguïsation explicite) ;
- ou le `redmine.project_id` **unique** — ex. `matnat-infra`.

**Jamais par match de slug nu.** Plusieurs clients partagent un même slug — ex.
`infra` chez `abatik`, `calicote`, `calyclay`, `matnat`, `pisceen`. Un résolveur
« premier slug trouvé » écrit **silencieusement dans le mauvais projet Redmine**
(incident RM2410 : `pm-wiki-sync infra` ciblait `abatik` au lieu de `matnat`).

**Conf = source de vérité, bloquante.** Chaque `meta.yml` de projet **doit**
déclarer un `redmine.project_id` **unique**. Absence ⇒ opération Redmine
**bloquée** (« pas de projet Redmine précis en conf → on n'avance pas »). Un slug
**ambigu** ⇒ **erreur** listant les candidats (`client/slug (redmine.project_id)`),
jamais de choix implicite.

**Outillage.** `PMConfig.resolve_project_ref(ref, require_redmine=True)` (lib
partagé `pm_paths`) : accepte `client/slug` ou `redmine.project_id`, lève sur
ambiguïté / introuvable / `redmine.project_id` absent. Tous les scripts qui
résolvent un projet pour une opération Redmine passent par lui (fin des boucles
`for … if proj == slug` locales).

## Filtrage IA — quels tickets Redmine sont synchronisés en MD

L'instance Redmine contient bien plus de tickets que ceux que PM doit
tracker. Pour éviter d'engloutir des centaines de tickets historiques en
MD (et leurs journaux) sans valeur ajoutée pour les agents, un **mutex
explicite** discrimine :

| Côté Redmine | Comportement PM |
|---|---|
| Ticket **sans** CF `IA` | Invisible pour PM. Aucun fetch, aucun MD, aucun sync. |
| Ticket **avec** CF `IA = "IA"` | Tracké par PM. MD local créé, sync bidirectionnelle active. |

**Mécanisme** : un custom field global de l'instance Redmine, type `List`,
nom `IA`, une seule valeur possible (`IA`). Présent sur tous les trackers
et tous les projets (`is_for_all: true`).

### Configuration

1. **Créer le CF** en UI Redmine (l'API REST ne supporte pas la création
   de custom fields, retourne HTTP 403) :
   - *Administration → Custom fields → Issues → New custom field*
   - Format `List`, Name `IA`, Possible values `IA`, Used as filter ✓,
     Searchable ✓, For all projects ✓, tous les trackers cochés
2. **Récupérer l'id** retourné, le stocker dans `.env` :
   ```
   REDMINE_CF_IA_ID=<id>
   ```
3. Documenté dans `.env.example`.

Si `REDMINE_CF_IA_ID` n'est pas défini, le filtre est **désactivé** (mode
rétrocompat : tous les tickets sont considérés trackables). Recommandé
uniquement pendant la phase de mise en place.

### Effet sur les scripts

| Script | Comportement quand le filtre est actif |
|---|---|
| `redmine-fetch-task.py` | Refuse de créer le MD si le ticket n'est pas tagué (sauf `--force`) |
| `redmine-fetch-updates.py` | Skip la sync si le ticket n'est plus tagué (signale le drift) |
| `pm-task-add.py` | Set automatiquement le CF `IA` au POST (les nouveaux tickets PM sont IA par construction) |
| `redmine-tag-ia.py` | Helper d'opt-in/opt-out : tag/untag un ticket existant, déclenche le fetch si nouveau tag |

### Opt-in d'un ticket existant

Pour faire entrer un ticket Redmine historique sous gestion PM :

```bash
./scripts/redmine-tag-ia.py <RM-id>           # tag + fetch + crée le MD local
./scripts/redmine-tag-ia.py <RM-id> --no-fetch # tag seulement, MD à créer plus tard
```

Pour le retirer :

```bash
./scripts/redmine-tag-ia.py <RM-id> --untag   # warning si MD local existe
```

### Règles d'intégrité

- **Pas de MD sans CF IA** : si un MD existe pour un ticket qui n'est pas
  tagué, c'est un drift à corriger (re-tag ou archive du MD).
- **Pas de CF IA sans MD** : un ticket tagué mais sans MD est en attente
  de fetch (`redmine-fetch-task.py --issue <id>` ou
  `redmine-tag-ia.py <id>` qui le déclenche).
- **Tag = consentement à la collecte** : les agents IA peuvent lire les
  journaux du ticket et appender au `.log.md`. Ne pas tagger les tickets
  contenant des données sensibles non destinées à un LLM tiers (Anthropic API).

### Test d'un ticket vis-à-vis du filtre

```bash
# Côté Redmine
curl -sS -H "X-Redmine-API-Key: $REDMINE_USER_MAIN_API_KEY" \
  "$REDMINE_URL/issues/<id>.json" | python3 -c "
import sys, json
issue = json.load(sys.stdin)['issue']
for cf in issue.get('custom_fields', []):
    if cf['name'] == 'IA': print(f'IA = {cf.get(\"value\")!r}')"
```

## Synchronisation de la configuration Redmine (obligatoire, périodique) — v1.21.0

Les IDs Redmine (statuts, trackers, priorités, custom fields, activités de
temps passé) sont **propres à chaque instance** et **mutables** : un admin
peut ajouter un statut, renommer un CF, créer une activité. Or PM les
**référence en dur** à plusieurs endroits :

- `.env` : `REDMINE_CF_IA_ID` (et autres IDs sensibles à venir)
- `knowledge/redmine/api.md` : mappings `NORMS_TO_REDMINE_STATUS`,
  `TRACKER_TO_TYPE`, et IDs des CF dédiés
- scripts : constantes (`CF_RAISON_FERME_ID = 11`, IDs CF ROI/tokens, …)

Un ID périmé fait **échouer silencieusement** un POST/PUT (CF ignoré) ou
mappe un mauvais statut. C'est une classe de bug difficile à diagnostiquer.

**Règle** : avant toute session qui touche à l'intégration Redmine (création
de tâche, sync de statut, push de métriques, bootstrap), et **a minima
périodiquement** (ou en cas de comportement inattendu), **revérifier que la
config locale colle à l'instance live**. En cas de drift → corriger `.env` /
`knowledge/redmine/api.md` / les constantes des scripts, puis committer.

**Quoi resynchroniser, et endpoints de référence** (lecture, clé API) :

| Dimension | Endpoint | Référence locale |
|---|---|---|
| Custom fields (issue **et** time_entry) | `GET /custom_fields.json` (admin) | `knowledge/redmine/api.md`, `.env`, constantes scripts |
| Statuts de ticket | `GET /issue_statuses.json` | `NORMS_TO_REDMINE_STATUS` |
| Trackers | `GET /trackers.json` | `TRACKER_TO_TYPE` |
| Priorités | `GET /enumerations/issue_priorities.json` | mapping priorité |
| Activités de temps passé | `GET /enumerations/time_entry_activities.json` | mapping type→activité (cf. § ROI) |

**CF dédiés actuels de l'instance iprospective** (issue sauf mention) — à
revalider lors du resync, ne pas présumer stables :

| ID | Type | Nom | Usage PM |
|---|---|---|---|
| 15 | list (issue) | `IA` | filtrage IA (cf. § Filtrage IA) |
| 21 | int (issue) | `Tokens prévus` | estimation tokens (cf. § ROI) |
| 22 | float (issue) | `Temps estimé IA (h)` | estimation temps IA |
| 17 | int (issue) | `Tokens passés` | cumul tokens effectifs |
| 16 | int (time_entry) | `Tokens` | tokens d'une saisie de temps (par commit) |
| 5 | int (issue) | `Gain/Perte (eq h dev/mois)` | gain ROI |
| 6 | int (issue) | `ROI` | ratio ROI |
| 11 | enum (issue) | `Raison Fermé` | `close_reason` |
| 20 | enum (issue) | `Task type` | taxonomie **fine** du `type` (cf. note ci-dessous) |

**Tracker (coarse) vs CF `Task type` (fin).** Le `type` NORMS est plus riche
(14 valeurs) que les 4 trackers Redmine (`Anomalie`/`Evolution`/`Assistance`/
`Tâche`). Le **tracker** porte la catégorie *coarse* (`TYPE_TO_TRACKER` :
`documentation`, `infrastructure`, `configuration`, `maintenance`, `autre`
retombent tous sur `Tâche`/4). Quand un type n'a pas de tracker dédié, son détail
est porté par le **CF 20 `Task type`** (enumeration) si une valeur correspond —
mapping **source unique** `redmine.reference.yml :: task_type_cf`
(ex. `documentation` → val 42, `configuration` → val 22 « Config »).
`pm-task-add` le pose à la création, `redmine-fetch-task` le relit (il **prime**
sur le tracker pour reconstituer le `type` fin). Ajouter une valeur d'énumération
côté Redmine + une ligne dans `task_type_cf` suffit à câbler un nouveau type fin.

> **Outillage** : `scripts/redmine-config-check.py` diffe la config live contre les
> références locales et signale tout drift — à lancer avant une session d'intégration
> Redmine ou périodiquement.

**Règle de propagation — source unique → consommateurs (v1.37.0).** Quand tu fais
évoluer un **paramètre canonique** (taxonomie de `type` et mappings
`TYPE_TO_TRACKER` / `type_to_activity` / `task_type_cf`, IDs Redmine, statuts,
priorités, énumérations…), mets à jour **dans le même changement** *tous* les
scripts et consommateurs qui le référencent — y compris ceux qui en dérivent une
liste pour l'UI. Préférer une **lecture à l'exécution** de la source (ex. le
cockpit karl-agent peuple son sélecteur de types via `pm-task-add --list-types`,
plutôt qu'une liste codée en dur) ; à défaut, le miroir est resynchronisé dans le
même commit. Une source de vérité et son miroir ne doivent **jamais diverger en
silence** — c'est la même classe de bug que le drift de config Redmine ci-dessus,
côté *écriture* cette fois. Avant de clore : vérifier la cohérence
`pm-task-add.py::TYPE_TO_TRACKER` ⇄ `redmine.reference.yml` ⇄ doc/UI.

> 📂 **Module `git-mep` — quand lire ceci :** je code un ticket (branche) · push / MR · projet versionné · commit+push · cycle dev→test→MEP.
> **Outils :** `glab`, `pm-branch-start` · **Préchargé par :** worker-dev, worker-db, worker-infra.

## Cycle de développement → test → mise en production (MEP)

Référence **canonique** du workflow de release applicatif, du dev d'un ticket
jusqu'à la prod. Le nommage des branches et le cycle de vie ne sont définis
**qu'ici** (la section *Architecture de déploiement* ne traite plus que de la
distribution des agents sur plusieurs machines).

### Branches git de référence (par projet)

Chaque projet déclare ses branches de référence dans le frontmatter de
`project/overview.md`, bloc `git:` :

```yaml
git:
  repo: <url-ou-alias>      # ex: git:sfy/pisceen-dercya/pisceen-prestashop.git
  remote: origin            # alias du remote de référence
  prod_branch: main         # branche de prod (main par défaut ; master si legacy)
  integration_branch: dev   # branche d'intégration : agrège les devs testés
  preprod_branch: preprod   # OPTIONNEL — déclaré ⇒ active le flux 3 branches (RM2030)
```

- `prod_branch` : **`main` par défaut**, `master` pour les repos legacy qui l'ont
  encore. Rien d'imposé — déclaré par projet ; la migration `master → main` se fait
  au fil de l'eau.
- `integration_branch` (`dev`) : agrège les branches de ticket déjà testées, avant MEP.
- `preprod_branch` (`preprod`) — **OPT-IN (RM2030)** : sa **présence** active le
  **flux 3 branches longues protégées** `dev → preprod → prod_branch` (cf. § Workflow
  MEP). **Absent ⇒ modèle 2 branches** `dev → prod_branch` (historique). C'est le
  **seul levier** : pas de flag séparé, pas de « bypass » — un projet qui ne veut pas
  de préprod ne déclare simplement pas `preprod_branch`.
- **Source unique** des branches de workflow : les `environments[].branch` doivent y
  être cohérents — `prod.branch == prod_branch` ; `staging.branch == preprod_branch`
  si déclaré, **sinon** `== integration_branch`.
- À distinguer du bloc `git:` du **frontmatter de tâche** (`git.branch`, `git.mr_url`),
  qui pointe la branche de *travail courante du ticket*, pas les branches de référence.

### Modèle d'environnements

Un projet a typiquement :
- **1 prod** (`prod`) — déployée depuis `prod_branch`.
- **1 staging** (`staging`, alias `preprod`) — déployée depuis **`preprod_branch`** si le
  projet est en **flux 3 branches** (opt-in), **sinon** depuis `integration_branch`.
  Tests de non-régression avant prod.
- **N test** (`test`, `test-<but>`…) — pour tester en parallèle plusieurs branches de
  ticket, idéalement par une personne ou un agent **≠ celui qui a fait le dev**.
- **N dev** (`dev`, `dev-<développeur>`…) — autant que de développeurs (voire plusieurs
  par dev).

Les noms custom (`test-2`, `dev-mathieu`) sont autorisés par l'enum `target_env`
(cf. § Valeurs énumérées). Chaque env est décrit dans `environments.md`.

### Identités & transport forge (multi-utilisateur) — v2.0.0

En multi-dev, l'identité forge est **par développeur**, plus « 2 identités karl » :

- **Identité par dev + fallback karl.** Les jetons forge se résolvent par la cascade des
  secrets (§ Multi-utilisateur & concurrence de `collaboration.md`) : token **perso** du dev
  (`~/.config/mmi-pm/.env`, `<FORGE>_<ROLE>_TOKEN`) d'abord, **karl** en repli commun. L'**API**
  forge (MR, protections) utilise ces PAT ; l'auteur d'une MR/branche est le dev, pas karl.
- **Transport SSH-first, token en repli.** Les remotes restent en **alias SSH canonique**
  (`gitlab:…`, `.gitmodules` inclus) ; le push/fetch passe par la clé forge dédiée du dev, avec
  **repli HTTPS+token** (`url.…insteadOf` global + credential helpers) quand la clé n'est pas
  disponible ou pour des submodules sans clé. **Ne pas** convertir les remotes par dépôt en
  HTTPS (casse les submodules) — l'`insteadOf` global obtient le même transport token.
- **Abstraction forge.** GitLab, **Gogs** (sans API PR → flux *lien-compare*, push HTTPS+token,
  SSH port 28022) et GitHub passent par la même abstraction `pm_forge` ; le backend se choisit
  par projet (`git config pm.forge`). Voir `pm-mr` / `pm-promote` / `pm-protect`.

### Workflow de développement (par ticket)

1. **Prise en charge** — ticket assigné à un agent ⇒ `en_cours` + auto-assignation
   Redmine (§ Prise en charge d'une tâche) + **création de la branche dédiée**
   `<RMid>-<short-desc>` (depuis `integration_branch`) + renseignement du CF Redmine
   `GIT Branche` (id 3). **Outil canonique : `pm-branch-start.py <RMid> --from
   <integration_branch> [--take]`** (RM1923) — crée/checkout la branche, pousse le
   CF, met à jour `git.repo`/`git.branch` du frontmatter + log, et `--take`
   enchaîne la prise (`pm-task-status-update en_cours`).
2. **Dev terminé** (ou étape) ⇒ `a_tester_dev` : test par un agent/une personne **≠ le
   dev**, dans un env `test`.
   - Test OK ⇒ `a_tester_demandeur` + ré-assignation au **demandeur**.
   - Problèmes ⇒ `a_corriger` (retour au worker).
3. **Validation demandeur** — le demandeur valide (test OK) ⇒
   - créer une **MR GitLab** depuis la branche du ticket `<RMid>-<desc>` vers
     `integration_branch` (`dev`) et renseigner son URL dans le CF Redmine **`GIT PR`**
     (id 4) — cette MR sert de **trace** du merge d'intégration ;
   - merge de la MR dans `integration_branch` ⇒ le ticket passe `a_mep` et entre dans
     le workflow MEP.
   - Rejet ⇒ `a_corriger`.

> Exception : un ticket sans code à déployer (doc, infra ponctuelle) peut aller de
> `a_tester_demandeur` directement à `ferme` (`close_reason: resolu`), sans MR ni MEP.

#### Commit + push systématique (obligatoire)

> **Auto-commit des scripts pm-\* (RM1834 piste A, v1.40.0).** Les scripts
> `pm-task-add/-status-update/-comment/-link/-sync/-report/-metrics-push`
> **committent et poussent eux-mêmes, atomiquement**, les fichiers qu'ils
> viennent d'écrire (module `scripts/pm_git.py` : `git commit -- <chemins>`
> sous verrou local, non-fatal ; interrupteurs `pm.config.yml :: git.autocommit`
> / `git.autopush`, flag `--no-commit` par appel). Conséquence : pour toute
> opération passée par un script PM, **tu n'as RIEN à committer toi-même** dans
> ai-projects. La règle manuelle ci-dessous reste obligatoire pour les **édits
> libres** (aspects, CDC, corps de tâche édités à la main) et le workspace de code.

> **Destination (RM2440).** Sur un **core**, le push va **directement sur la branche
> de prod** — ni repli `dev`, ni promotion, donc pas d'arriéré. Un rejet
> **non-fast-forward** y est rattrapé par `pm_git` (fetch + `rebase --autostash` sous
> verrou, puis re-push) ; sur **conflit** : `rebase --abort` + warning. Levée **ciblée**
> de l'invariant « pas de rebase dans l'arbre partagé » — cores seulement ; **code**
> inchangé. Auto-commit réussi = **silencieux** (`git.verbose: true` pour
> déboguer), cf. `worker-common` § Restitution.

Toute modification d'un fichier rattaché à un projet PM **doit être suivie
d'un `git add <fichiers> && git commit && git push` immédiat**, dans le repo
git approprié. La règle s'applique à **deux périmètres** :

1. **Dossier projet PM côté `{projects_root}` (= ai-projects)** : `overview.md`,
   aspects, fichiers de tâche `RM*.md`/`.log.md`, ou structure d'entité
   (`client/`, `memory/`). Repo cible :
   `gitlab:iprospective/ai-artificial-intelligence/ai-projects.git`.

2. **Workspace de code lié au projet** côté `/zfs/workspaces/<...>/` — identifié
   par la **paire de symlinks** :
   - côté PM : `{paths.workspace_link}` (typiquement `…/projects/<slug>/workspace`)
     pointe vers le workspace
   - côté workspace : `{paths.reverse_link}` (`.mmi-pm`) pointe vers le projet PM

   Tout fichier modifié dans ce workspace (code, conf, docs internes) doit être
   commit+push dans le repo applicatif du workspace lui-même (remote GitLab
   canonique `git:`/`gitlab:iprospective/<...>`, **pas** ai-projects ; cf.
   « Remote canonique GitLab » ci-dessous).

**Règles communes aux deux périmètres** :
- Stager **uniquement** les fichiers touchés (jamais `git add .` ou `-A`),
  pour ne pas embarquer d'autres modifs en cours non liées qui ne sont pas
  de ta responsabilité — chacun est responsable de ses propres modifs.
  **Vérification active au commit (obligatoire) — v1.29.0, généralisée v1.30.1** :
  **tous les repos partagés** — `ai-projects` **comme le repo système
  `project-management`** (NORMS, `templates/`, `scripts/`, `pm.*.yml`) et **le
  workspace de code** — sont **fréquemment dirty en concurrence** (plusieurs
  sessions/agents en parallèle laissent des fichiers modifiés ou non suivis qui ne te
  concernent pas ; ex. typique : `pm.pricing.yml`, `pm-task-tick.py` modifiés par une
  autre tâche pendant que tu édites NORMS). La règle « ne committer que ses propres
  modifs » vaut donc **dans chaque repo, sans exception**. Avant tout
  commit : (1) stager par **chemin explicite** les seuls fichiers de la tâche
  courante (pas de glob large qui ratisse) ; (2) **relire le set stagé**
  (`git diff --cached --name-only`) et confirmer que **chaque** entrée concerne bien
  cette tâche ; (3) committer seulement alors. Ne **jamais** committer un fichier
  qu'on n'a pas soi-même modifié dans la session courante, même s'il apparaît dirty
  (ni un fichier non suivi appartenant à une autre tâche). Une solution d'isolation
  propre (workspaces instanciés par projet / zones de stash temporaires) est **à
  l'étude** — cf. ticket dédié
- Message de commit court, dans la langue du repo, précisant
  l'entité/projet/tâche concerné
- Push systématique : pas de "je commit, le user pushera" — le repo doit
  refléter l'état canonique à tout moment, sinon les autres agents (ou toi
  dans une session future) travaillent sur une vue divergente
- Si le push échoue (conflit avec `origin/<branche>`), `git pull --rebase`
  puis re-push ; en cas de conflit non trivial, escalader au demandeur
- Ne **jamais** committer un dossier projet PM dans le repo
  `project-management/` lui-même : `projects/` est gitignored par construction
  (cf. section précédente)
- Si le workspace de code n'est pas (encore) un repo git, c'est probablement
  une lacune de bootstrap — ouvrir/relancer la tâche `002-git-repos` du
  bootstrap plutôt que de "skipper" le commit

Cette règle s'applique à tous les agents (workers, summarizer, reviewer, et
agents pilotés interactivement par l'utilisateur via Claude Code).

#### Branche de travail par ticket (obligatoire) — v1.17.0

Tout travail de code rattaché à un ticket PM se fait sur une **branche dédiée
au ticket**, jamais directement sur la branche d'intégration (`main`, `19.0-mmi`,
etc.). Convention de nommage **systématique** :

    <RM-id>-<slug-court>

où `<RM-id>` est l'identifiant Redmine (sans préfixe) et `<slug-court>` un
résumé court en kebab-case du sujet (≈ 2-4 mots, **pas** le titre complet de la
tâche). Exemple : `1762-etransactions-historique`.

- La branche est créée depuis la branche d'intégration courante du repo de code.
- Le frontmatter `git.branch` de la tâche pointe vers cette branche (cf. section
  « Lien Redmine ↔ MD ») ; `git.mr_url` vers la MR/PR une fois ouverte.
- **Renseigner le custom field Redmine « GIT Branche » dès la création de la
  branche** (v1.18.0) : le CF Redmine `GIT Branche` (id 3, format string) reçoit
  le **nom de la branche** ; le CF `GIT PR` (id 4) reçoit l'URL de la MR/PR une
  fois ouverte. C'est le CF dédié, **pas une note** : il rend l'info visible et
  filtrable côté Redmine. Le frontmatter MD `git.branch` / `git.mr_url` reste le
  miroir local.
- **À la livraison : MR sur le remote, et on CONSERVE la branche distante.**
  La livraison d'une branche de ticket vers l'intégration se fait **via une
  Merge Request** GitLab — **pas** un merge poussé en direct sur la branche
  d'intégration. Et **la branche distante est conservée après merge** (jamais
  supprimée) : elle garde la trace de revue/livraison et un point de référence
  par ticket. ⚠️ Distinguer **autoriser un merge ≠ autoriser une suppression** :
  ne **jamais supprimer une branche distante** sans accord explicite.
- **Ménage : seulement en local.** Les branches **locales** mergées peuvent
  (doivent) être nettoyées (`git branch -d`), le **remote** restant la référence
  conservée. Le ménage local ne touche jamais au remote.
- (Multi-serveur V2) le schéma `agent/{server}/RM{id}-titre` reste l'exception
  réservée à l'orchestration distribuée ; en mono-machine, utiliser la forme
  courte ci-dessus.

#### Plusieurs tickets dans une session : bonne branche, bon worktree — v1.20.5

Une session peut légitimement toucher **plusieurs tickets à la fois** (correctifs
groupés, dépendances croisées, lot de validation…). Le risque concret — **déjà
survenu** : committer le travail d'un ticket sur la **branche d'un autre** parce
que le working tree était resté checké out dessus (ex. un commit « dashboard
RM2011 » atterri sur la branche `RM2020` du graphe). À éviter :

- **Avant chaque commit, vérifier la branche courante** (`git branch --show-current`)
  et qu'elle correspond bien au ticket dont on commite le travail. Un seul working
  tree + bascules de branche = source d'erreur quand on jongle.
- **Un worktree par ticket plutôt que des `checkout` successifs.** Quand on mène
  plusieurs tickets en parallèle, créer un **git worktree dédié** par ticket via
  **`pm-branch-start <RMid> --worktree`** (RM2034) : il crée le worktree
  `<repo>-<RMid>-s<seq>`, une branche **discriminée par session**
  `<RMid>-<slug>-m<PMid>-s<seq>`, et **enregistre** branche + worktree dans le
  registre de session. Chaque ticket a sa branche dans son propre dossier : on ne
  se trompe plus de cible et on ne réécrit pas le working tree d'une autre tâche.
  Ménage à la livraison : **`pm-worktree remove <path>`** (git worktree remove +
  purge du registre).
- **Mapper branche/worktree ↔ session.** L'id de session court (`s<seq>`, alloué
  une fois sous flock — RM2034) + l'id machine (`m<PMid>`, `PM_MACHINE_ID` du
  `.env`) **discriminent** la branche/worktree pour que **deux sessions sur le même
  ticket ne se marchent pas dessus**. Le registre `var/sessions/` mémorise les
  branches/worktrees ouverts ; **`pm-session-status show`** les liste. La forme
  courte `<RMid>-<slug>` (sans `--worktree`) reste la norme **hors concurrence**.

> 📂 **Module `git-mep-pratique` — quand lire ceci :** je prépare une MEP · je bute sur le transport git (SSH/token, submodules) · l'API GitLab répond de travers · ticket d'interface · projet versionné · une base de dev partagée me surprend.
> **Outils :** `pm-mr`, `pm-promote`, `glab` · **Préchargé par :** *(personne — ouvert à la demande)*.

# Git / MEP — mode d'emploi et cas particuliers

Détaché de `git-mep.md` par RM2582 : ces sections sont du **mode d'emploi** et
des **cas particuliers**, pas des règles à connaître en permanence. Elles
pesaient sur le contexte de tous les workers alors qu'elles ne servent qu'au
moment précis où le déclencheur se présente. Les règles quotidiennes (commit +
push, branche par ticket, plusieurs tickets par session) sont restées dans
`git-mep.md`.

#### Ticket d'INTERFACE : éprouver sur la branche, promouvoir une seule fois

Un ticket qui touche une **interface** (cockpit karl-agent, et par extension toute
UI) se valide dans une **instance de test montée sur la branche**, **avant** toute
promotion — puis **une seule** promotion vers la prod et **une seule** MEP pour le
lot de tickets éprouvés ensemble.

**Outil canonique : `pm-cockpit-test-env.py create <RMid>`** — instance dédiée sur
le worktree de la branche (port propre, `test_url` posée sur le ticket) ;
`teardown <RMid>` pour l'arrêter.

**Pourquoi** : une interface produit des défauts que le test unitaire ne peut pas
voir — ils ne se manifestent qu'à l'usage. Promouvoir ticket par ticket fait alors
du **demandeur l'environnement de test** : chaque retour coûte un cycle complet
(snapshot, MEP, redémarrage, rechargement). Constat RM2453 : sept tickets cockpit
promus un par un, puis trois chantiers groupés absorbant six retours d'usage sans
qu'un octet ne bouge en production — dont trois vrais défauts invisibles aux tests
(une tuile non sélectionnable, des sessions closes listées, une vue s'appropriant
les sessions d'un autre client).

Deux propriétés de l'instance de test à connaître : son **état d'instance**
(`LOG_DIR`) est **isolé** — on peut tout y casser —, mais l'**état de session**
(`STATE_DIR`) est **partagé** avec la prod : les sessions manipulées sont les
vraies. Et l'auth y étant ouverte, l'utilisateur courant y est le superadmin, non
le compte nommé.

### Workflow de mise en production (MEP)

La MEP opère sur la **branche d'intégration entière** (`integration_branch`), pas
ticket par ticket : plusieurs tickets en `a_mep` montent ensemble. Le chemin dépend du
**modèle de branches** du projet (cf. § Branches git de référence).

**Flux 3 branches** (opt-in : `preprod_branch` déclaré) — **`dev → preprod → prod_branch`**.
Les 3 branches longues sont **protégées** ; règle stricte **« merge only from »** :
`preprod` n'est mergeable **que depuis `dev`**, et `prod_branch` **que depuis `preprod`**
(jamais une MR `dev → prod_branch` en direct). Promotion **par MR**, branches conservées.

1. **MR `dev → preprod`** ⇒ déployer `preprod_branch` en preprod ⇒ tickets `en_mep`.
2. Tests de **non-régression** sur preprod + vérification par un **testeur humain**.
3. Si OK ⇒ **MR `preprod → prod_branch`** + `pull prod_branch` en prod ⇒ tickets `ferme`
   (`close_reason: resolu`).
   - Régression preprod ⇒ `a_corriger` (note obligatoire).

**Deux modes de promotion :**
- **Pas-à-pas** (défaut) : halte en preprod pour la non-régression avant de promouvoir en prod.
- **Enchaîné (auto)** : une action outillée déroule `dev → preprod → prod_branch`
  d'affilée, **sans halte manuelle** en preprod — l'équivalent « rapide » **sans
  déroger** au modèle (preprod reste traversée). C'est cet enchaînement qui tient lieu
  de « bypass » : il n'existe **pas** d'option pour *sauter* preprod.

**Flux 2 branches** (pas de `preprod_branch`) — **`dev → prod_branch`** (historique) :
`integration_branch` déployée en staging, tests de non-régression, puis **MR
`dev → prod_branch`** + `pull prod_branch`.

> **⚠️ Règle de sécurité prod — consentement explicite obligatoire.** Aucune commande
> susceptible de modifier ou casser la **production** ne doit être **exécutée sans le
> consentement explicite de l'humain pour cette action précise**. Sont visés notamment :
> merge vers `prod_branch`, `git pull`/`reset`/`checkout` sur un serveur de prod,
> exécution d'une migration ou d'un upgrade de module, vidage de cache prod, restart de
> service, toute écriture de fichier en prod. L'agent **inspecte** (lectures seules) et
> **propose la commande exacte**, puis attend le feu vert. Un accord pour une étape ne
> vaut **pas** pour les suivantes. Avant toute écriture, **vérifier l'état réel du
> serveur** (branche suivie, remote source réel, propreté de l'arbre) : un arbre de prod
> sale ou une source de déploiement divergente sont des **signaux d'arrêt**, à remonter
> à l'humain plutôt qu'à forcer.
#### Point de restauration avant MEP — infra opensvc / LXC / ZFS (obligatoire)

Quand la cible tourne sur une infra **opensvc + conteneurs LXC sur datasets ZFS**
(cas du parc iProspective), **prendre un snapshot ZFS du conteneur AVANT toute mise
en production** — upgrade applicatif, migration, changement de conf, recréation de
conteneur. Le snapshot est pris **depuis l'hôte** (nœud sur lequel le service tourne,
cf. `om <svc> print status`), pas depuis le conteneur :

```bash
om <svc> sync update --rid sync#root_hour     # déclenche la ressource zfssnap "hourly"
om <svc> sync all    --rid sync#root_hour     # variante : toutes les actions de sync de la ressource
```

Vérifier que le snapshot existe avant de continuer :
`zfs list -t snapshot -o name,creation -s creation | grep '<dataset>@hourly'`.

**Ce snapshot tient lieu de sauvegarde préalable** : il couvre le rollback complet du
conteneur (données + configuration + état applicatif), donc **inutile d'empiler un
dump applicatif ad hoc** (mysqldump & co) « au cas où ». Le régime de snapshots
multi-cadence + réplication assure par ailleurs la conservation longue.

Points de vigilance :
- La ressource `sync#root_hour` a une **rétention courte** (`keep = 8` sur le parc,
  soit ~8 h) : le snapshot pré-MEP n'est un filet **que sur la fenêtre d'intervention**.
  Pour une MEP dont on veut garder le point de retour plus longtemps, s'appuyer sur les
  cadences `sync#root_day` / `sync#root_week`, ou créer un snapshot nommé dédié.
- Le nom du snapshot créé est **loggué dans le `.log.md`** du ticket, avec la procédure
  de rollback (cf. `modules/traceability.md`) — un point de restauration non tracé ne
  sert à rien le jour où il faut revenir en arrière.

> **Trou d'outillage** (à combler) : pas encore de script PM dédié
> (`pm-snapshot-pre-mep`) — la commande `om` est passée à la main pour l'instant.

> Le **modèle de branches** ci-dessus est arrêté (RM2030) — plus « provisoire ». Restent
> à outiller / faire évoluer : le **mécanisme de déploiement** (aujourd'hui `pull`
> manuel → CI/CD, rollback) et l'**enforcement** de la règle « merge only from »
> (aujourd'hui **convention NORMS + protections GitLab** sur `preprod`/`prod_branch` ;
> **garde CI / push-rule** = follow-up, GitLab ne sachant pas nativement « mergeable
> seulement depuis X »). Cf. `project/deployment.md` (template `005-deployment`).

---
#### Remote canonique GitLab, MR, et gotchas API — v1.58.2

- **GitLab est le remote canonique** : quand un repo de code a un remote GitLab
  (typiquement `origin`, alias SSH `git:`/`gitlab:` → `gitlab.iprospective.fr`),
  c'est lui qu'on utilise **par défaut** pour push, branches et MR. C'est aussi lui
  que traque la branche d'intégration locale.
- **Transport git = SSH + alias, premier choix partout** : le push/fetch passe par
  l'**alias SSH** (`gitlab:<chemin>.git`, résolu via `~/.ssh/config`). C'est la forme
  **canonique et préférée** du remote sur **tous** les repos PM — on ne convertit
  **pas** les remotes en HTTPS. L'auth repose sur une **clé GitLab dédiée sans
  passphrase** (`~/.ssh/id_ed25519_gitlab`, `IdentitiesOnly yes` ; clé sur `karl-dev`,
  identité worker), donc **toujours disponible sans ssh-agent** — choix délibéré : un
  agent ne survit pas au reboot et personne ne peut le déverrouiller en session
  autonome (**RM2158**). HTTPS + credential-helper token n'est qu'un **repli** quand
  cette clé n'est pas disponible sur la machine ; ce n'est **pas** la cible.
- **Ce repli HTTPS+token se pose par `url.…insteadOf`, PAS par conversion de remote
  (RM2328, PoC)** : sur une machine **sans** la clé `karl-dev` (ou pour forcer le token
  — agent d'automatisation tiers, ou submodules à tirer sans clé), **ne convertis pas**
  les remotes. Pose un `url.…insteadOf` **global** dans le `~/.gitconfig` de l'agent : il
  réécrit `gitlab:` / `git@gitlab.iprospective.fr:` / `ssh://git@…` →
  `https://gitlab.iprospective.fr/` **au moment de l'op**, servi par le credential-helper
  token. Push, fetch **et submodules** passent alors en token **sans muter aucun remote
  ni `.gitmodules`** (le remote stocké reste `gitlab:` ; démontré : PoC RM2328). Une
  config **par machine**, réversible, **par-utilisateur** (n'affecte que l'environnement
  où elle est posée).

  ```bash
  git config --global --add url."https://gitlab.iprospective.fr/".insteadOf "gitlab:"
  git config --global --add url."https://gitlab.iprospective.fr/".insteadOf "git@gitlab.iprospective.fr:"
  git config --global --add url."https://gitlab.iprospective.fr/".insteadOf "ssh://git@gitlab.iprospective.fr/"
  git config --global credential.helper <helper-token>   # worker (code) / manager (PM & protégés)
  ```

  ⚠ Ne **pas** faire `git remote set-url … https` par repo — ça casse les configs SSH
  partagées (submodules) ; l'`insteadOf` global obtient le même transport token sans y toucher.
- **Pourquoi ça compte — panne silencieuse si l'auth SSH casse** : si la clé/config
  est absente ou le membership GitLab manquant, deux effets sournois — (1) le **push
  se reporte** (« push différé » qui s'accumule) ; (2) `git fetch` peut **échouer en
  silence** → la ref `origin/*` reste **périmée** et annonce la branche « à jour »
  alors qu'elle a divergé, ce qui fait **mentir l'anti-collision** de `governance`
  (elle raisonne sur `git fetch`). ⇒ toujours `git fetch` **et vérifier son succès**
  avant un bump de version ; la santé « karl peut pousser » (`ssh -T gitlab`) est
  surveillée au cockpit (watchdog **RM2376**, cf. **RM2158** / **RM2328**).
- **Ne pas confondre transport et API** : l'**API GitLab** (création/merge de MR,
  `pm-protect`, résolution de projet) utilise **toujours les PAT** (`pm-mr`, tokens
  worker/manager du `.env`), en **HTTPS**, indépendamment du choix SSH pour le
  transport git. SSH-first ne concerne que push/fetch, pas les appels API.
- **Miroir gogs déprécié** : le miroir `gogs:` est **déprécié de manière
  générale**. Il reste actif **uniquement sur le projet `pisceen/prestashop`**.
  Partout ailleurs, ne plus pousser vers gogs (ni le maintenir en sync) — tout
  passe par GitLab.
- **Livraison par MR** (pas de merge direct sur la branche d'intégration) : créer
  une merge request de la branche de ticket vers la branche de base (version
  active ou `dev`, cf. sous-sections suivantes), puis la merger — **branche
  distante conservée** (cf. KERNEL #3).
- **Aucun commit/push direct sur une branche protégée d'un dépôt de CODE** (KERNEL #3)
  — dès le flux 2 branches : `dev` **et** prod ne reçoivent que des **merges de MR**,
  promotion comprise. Un commit direct sur `main` court-circuite la promotion →
  divergences et **collisions de version NORMS** (vécu : RM2035/2038/2048). Les **cores**
  ont leur propre régime (tableau ci-dessous).
- **Enforcement GitLab — outil `pm-protect` (RM2052, étendu RM2440)** : `pm-protect
  [--repo PATH | --project-id N | --all-cores]` applique la politique de protection
  (idempotent, `allow_force_push=false`, branche absente ignorée), token *manager*.
  **Deux politiques**, selon la nature du dépôt :

  | Branche | Dépôt de **code** | Dépôt **core** |
  |---|---|---|
  | prod (`main`, ou `master`) | push **personne** / merge Maintainer | push **Developer** / merge Maintainer |
  | intégration (`dev`) | push Maintainer / merge Maintainer | idem — conservée, sans trafic |
  | `preprod` (flux 3 branches) | push **personne** / merge Maintainer | — |

  Core : `push=Developer` = le niveau de l'identité qui pousse (`karl-dev`, *worker*).
  ⚠ **`push=Maintainer` y équivaut à `push=personne`** — piège à l'origine de l'arriéré
  de juillet 2026. **Prérequis** : le compte *manager* doit être
  **Maintainer sur le projet**, sinon `403` (vérifier le membership, pas l'outil).
  ⚠ **Dépôt neuf : l'appliquer aussitôt** — il n'hérite que du défaut GitLab (`main` :
  push *Maintainer*), qui ressemble à une protection conforme sans en être une. (RM2568)
  Depuis **RM2057**, `pm-project-new` s'en charge automatiquement pour les dépôts qu'il
  crée ou trouve déclarés (étape 5b, non bloquante) : le geste manuel ne reste requis
  que pour un dépôt créé hors de ce flux.
- **Outil canonique : `pm-mr`** (RM1871) — `pm-mr create <RMid>` (push + MR + CF) /
  `pm-mr merge <iid>` (merge, conserve la branche) / `pm-mr get <iid>`. Il encapsule
  les gotchas ci-dessous (ID numérique, en-tête, re-GET de confirmation). À préférer
  au `glab` brut. `pm-branch-start` (crée la branche) + `pm-mr` couvrent le cycle git.
  Il vaut pour **tout** dépôt, **même hors conf PM** (module en
  submodule, dépôt neuf) : lui passer l'**URL de la MR** ou `--repo`. Ne pas conclure
  qu'il « ne couvre pas ce cas » sans essayer — le repli par API inline perd les
  gotchas **et** peut être refusé par le **harnais de l'agent**, refus qu'on prend
  pour un refus GitLab. (RM2568)
- **Deux identités GitLab de karl, deux PAT dans `.env`** : la frontière calque les
  rôles GitLab.
  - `GITLAB_MANAGER_TOKEN` (+ `GITLAB_MANAGER_USER`) — karl **manager** (rôle
    *Maintainer*) : **merge** les MR, gère les projets. Utilisé par `pm-mr merge` et
    la promotion MEP.
  - `GITLAB_WORKER_TOKEN` (+ `GITLAB_WORKER_USER`) — karl **worker** (rôle
    *Developer*) : push des branches, **crée** des MR. Utilisé par `pm-branch-start`
    et `pm-mr create`.
  - Source canonique = le `.env` de **`.mmi-pm-core`** (machine-local, jamais
    commité). PAT scope `api`. **Ne pas** dépendre du token OAuth de `glab` (se
    révoque ; mauvais en-tête → 401/404).
  - **Split clone-dev / runtime (RM2051)** : le **clone de dev** (`PM_DEV_DIR`) ne
    porte **pas** de `.env` (secrets uniquement dans `.mmi-pm-core`). `PMConfig` charge
    le `.env` de `pm_dir` s'il existe (runtime canonique, via le symlink), **sinon**
    celui du core pointé par **`PM_CORE_DIR`** ; à défaut, **erreur explicite**. Donc :
    lancer les scripts à secrets **depuis le runtime** (symlink), ou exporter
    `PM_CORE_DIR=<.mmi-pm-core>`, ou sourcer le `.env` canonique.
- **Rotation des tokens (RM2046)** : PAT à expiration → rotation **J-7** (tous les
  `GITLAB_*_TOKEN`, pas que le manager). En début de session PM, **`pm-token-check`**
  rapporte l'expiration (valeur jamais imprimée ; RC=2 si l'un est sous le seuil) ;
  **`--rotate-due`** rote et réécrit le `.env` canonique atomiquement (tripwire #11).
  Options : `--threshold`, `--rotate-expiry-days` (365), `--dry-run`.
- **Accès projets** : karl peut **créer** des projets GitLab (il en est alors
  membre), mais **n'a pas automatiquement accès aux projets existants** — il faut
  l'**ajouter comme membre** (rôle *Developer* pour le worker, *Maintainer* pour le
  manager) sur chaque projet pré-existant à piloter.
- **Gotchas API GitLab** (gérés par `pm-mr`, à connaître si appel direct) :
  - **`%2F` rejeté** par le front Apache (`projects/iprospective%2F…` → 404) →
    utiliser l'**ID numérique** (`GET /projects?search=<nom>` sans slash).
  - **En-tête d'auth** : un **PAT** passe en `PRIVATE-TOKEN:` (un token OAuth `glab`
    en `Authorization: Bearer` ; sinon 404 sur repo `internal`).
  - **Corps vide sur succès** possible → **re-GET** pour confirmer l'état.
  - **Conserver la branche** au merge : `should_remove_source_branch=false`.
- **Tracer dans le ticket** : une fois la MR créée, renseigner le CF Redmine
  `GIT PR` (id 4) avec son URL (`pm-mr create` le fait).
#### Base de dev partagée entre worktrees : ne pas confondre avec une anomalie

En layout worktrees (RM1993/RM2267), **les fichiers sont par branche mais la base
de données de dev est partagée** par tous les worktrees du projet. Un module, une
entité ou une configuration peut donc être **enregistré et actif en base** alors
que **ses fichiers sont absents du worktree courant** — parce qu'ils vivent sur la
branche d'un autre ticket, pas encore mergée.

Cas réel (2026-08-01, `calicote/prestashop`) : un module apparaissait « installé,
actif, 6 hooks » en base, avec **0 fichier sur disque**. Diagnostic tentant :
module fantôme, enregistrement à nettoyer. **Faux** — ses fichiers étaient dans
deux autres worktrees, sur des branches en cours.

Le risque n'est pas la perte de temps : c'est de **« corriger » une fausse
anomalie** en désinstallant un enregistrement légitime, et de casser le travail
d'une autre session.

> **Règle.** Avant de qualifier d'anomalie un écart **base ↔ fichiers**, chercher
> les fichiers **dans les autres worktrees du projet** :
>
> ```bash
> for d in <workspace>/envs/*/; do
>   printf '%-34s %-40s %3s fichiers\n' "$(basename "$d")" \
>     "$(git -C "$d" rev-parse --abbrev-ref HEAD 2>/dev/null)" \
>     "$(find "$d/<chemin>" -type f 2>/dev/null | wc -l)"
> done
> ```
>
> S'ils y sont : ce n'est **pas** une anomalie, c'est du travail en cours sur une
> autre branche. Ne rien toucher, et vérifier qu'aucun ticket n'est ouvert dessus
> avant d'intervenir.
#### Projets versionnés : branche de version active (base de branchement) — v1.20.0

Certains projets ne suivent pas un simple modèle `prod`/`dev` mais une **famille
de versions**, chacune avec sa propre branche d'intégration. C'est typiquement le
cas des projets et **modules Dolibarr** : en plus de `dev` (= prochaine version)
et `master`, il existe une **branche par version** (`14.0`, `15.0-mmi`,
`16.0-mmi`, `19.0-mmi`…), et l'une d'elles est la **version active** = celle
déployée en production.

Le modèle de versionnement est **déclaré dans le frontmatter de l'`overview.md`
du projet** via le bloc `versioning` (absent ⇒ projet non versionné, modèle
`prod`/`dev` classique) :

```yaml
versioning:
  scheme: dolibarr        # type de versionnement (ou null)
  active_version: "19.0"  # version déployée en production
  active_branch: 19.0-mmi # branche d'intégration de la version active (base des tickets prod)
  next_branch: dev        # branche de la prochaine version (base des tickets next-version)
```

- Pour un module appartenant à un écosystème (ici Dolibarr), `active_version` suit
  celle de l'application hôte.
- Le choix de la **branche de base** d'un ticket dépend de la cible :
  - ticket `feature`/`fix` **pour la prod actuelle** → partir de `active_branch`
    (ex. `19.0-mmi`) ;
  - ticket **réservé à la prochaine version active** → partir de `next_branch`
    (ex. `dev`).
- La branche de ticket `<RM-id>-<slug-court>` est tirée de cette branche de base
  et y est remergée à la livraison : la branche de base joue alors le rôle de
  « branche d'intégration » au sens de la sous-section précédente.
- En cas de doute sur la cible (prod actuelle vs prochaine version), **demander
  avant de brancher** : se tromper de base impose un rebase/cherry-pick ultérieur.
> 📂 **Module `roi-pricing` — quand lire ceci :** j'estime · je calcule le ROI · je priorise · journalisation temps/tokens par commit.
> **Outils :** `pm-task-add`, `pm-task-tick`, `priority.py`, `pm-task-report` · **Préchargé par :** orchestrateur.

## Ordonnancement par ROI

Script `scripts/priority.py` qui calcule pour chaque tâche `a_faire` :

```
score = (immediate_benefit + monthly_benefit * 12) * priority_weight / max(estimate.time_minutes, 1)
```

Avec `priority_weight = {low: 0.5, normal: 1, high: 2, urgent: 4}`.

Filtre : tâches `a_faire` dont toutes les `depends_on` sont `ferme`.
Sortie : top N tâches triées par score décroissant, par client/projet ou global.

## ROI assisté par IA (RM1717)

Chaque ticket porte un coût (tokens IA + temps humain) et un gain
(immédiat + récurrent). Le ROI se calcule à partir de ces 4 dimensions.

### Tarification

Les prix par modèle sont dans `pm.pricing.yml` (commitable, à maintenir
quand Anthropic ajuste). Unités : **USD/MTok** pour input/output/cache,
**EUR/h** pour le coût humain.

### Frontmatter étendu (v1.11.0)

```yaml
# Estimation prévisionnelle
estimate:
  difficulty: medium                  # inchangé
  human_time_minutes: 30              # NEW — temps humain prévu (revue, décisions, tests)
  ai_time_minutes: 15                 # NEW — temps wall-clock IA prévu
  tokens: 50000                       # tokens prévus (total)
  cost_usd: 0.75                      # NEW — coût USD prévu (estimé depuis tokens × prix)
  estimated_model: claude-opus-4-7    # NEW — modèle prévu (pour calcul cost prévu)
  confidence: 0.6
  estimated_by: pm-task-add
  estimated_at: 2026-05-17T14:30

# ROI — les deux échelles coexistent
roi:
  immediate_benefit: 3                # 1-5 — rapide à estimer (qualitatif)
  monthly_benefit: 3                  # 1-5 — récurrent qualitatif
  immediate_gain_eur: null            # NEW — gain € immédiat (one-shot)
  monthly_gain_eur: null              # NEW — gain € récurrent mensuel
  # yearly_gain_eur dérivé = monthly_gain_eur × 12 (pas stocké)

# Cumulés effectifs (auto-incrémentés par le hook pm-task-tick)
tokens_total: 0                       # somme tous types
tokens_breakdown:                     # NEW — détail par type
  input: 0
  output: 0
  cache_read: 0
  cache_creation: 0
cost_total_usd: 0.0                   # NEW — cumulé recalculé à chaque tick
human_time_total_minutes: 0           # NEW — temps humain effectif
ai_time_total_minutes: 0              # NEW — temps wall-clock IA effectif
```

### Auto-incrémentation (hook Claude Code Stop)

Le hook `~/.claude/hooks/pm-task-tick.py` est déclenché à la fin de chaque
réponse Claude. Il :

1. Lit l'event JSON sur stdin (`session_id`, `transcript_path`, `cwd`, …)
2. Identifie le RM-id courant **par ce que le tour a réellement touché** (RM1823),
   lu dans le transcript que le hook reçoit déjà — on ne **devine** pas le ticket
   depuis l'état du projet :
   - **Signal du tour** (events depuis le dernier prompt humain, celui-ci inclus) :
     le candidat au signal le plus **fort**, puis le plus **récent**. Force du
     signal : **3** = commande de mutation PM (`pm-task-*.py`, `redmine-*.py` avec
     un RM-id), **2** = édition d'un fichier de ticket (`RM<id>_*.md`), **1** =
     simple mention textuelle (`RM1234`).
   - **Continuation** : si le tour n'a touché aucun ticket (question, lecture,
     mise au point), on retombe sur le dernier ticket touché **de la session**.
   - **Repli** : sentinel projet `<workspace>/.mmi-pm/CURRENT_TASK`.
   - **Le statut n'entre PAS dans la résolution** — sauf la garde `ferme`
     ci-dessous. Une phase d'`etude_chiffrage_en_cours`, un `a_corriger`, un
     `a_mep` sont tickés comme un `en_cours` : l'étude et le chiffrage se
     mesurent aussi. (L'ancienne heuristique « seule tâche `en_cours` du projet »
     est abandonnée depuis RM1823 : trompeuse — plusieurs tâches `en_cours` dans
     un projet est le cas NORMAL, comme plusieurs sessions en parallèle ou
     plusieurs tickets dans une même session.)
   - **Garde « ticket fermé » (RM2053)** : la cible n'est **jamais** un ticket
     `status: ferme`. Le résolveur retient le signal le plus fort **parmi les tickets
     ouverts** ; un tour touchant un ticket ouvert + un fermé ticke l'**ouvert** ; un
     tour ne touchant que du fermé → **aucune tick** (la conso du tour est perdue,
     négligeable). Un sentinel `CURRENT_TASK` pointant un ticket clos est ignoré.
     **Fail-safe** : statut illisible → traité comme ouvert (mieux vaut ticker que
     perdre). Évite que la cérémonie de clôture / le suivi post-fermeture ne gonfle un
     ticket déjà fermé.
3. Si aucune cible identifiée → log dans `~/.claude/logs/pm-task-tick-untracked.jsonl` et exit propre
4. Sinon : somme les tokens **de tous les messages assistant du tour** (fenêtre =
   curseur de session, à défaut dernier prompt humain — jamais tout le transcript,
   pour ne pas recompter l'historique d'une session reprise), **dédupliqués par
   `message.id`** (RM2628 : le JSONL écrit une même réponse une fois par bloc de
   contenu, chaque ligne portant l'usage complet ; sans dédup la conso est
   multipliée par le nombre de blocs — règle partagée avec le cockpit via
   `pm_transcript.usage_by_message`), calcule le coût USD via `pm.pricing.yml`,
   met à jour le frontmatter du MD (atomique avec optimistic locking)
5. Append au `.log.md` une entrée concise (seuil : >1000 tokens total pour
   éviter le bruit, sinon silencieux)

### Calcul du ROI

```
invest_eur = cost_total_usd × usd_to_eur + (human_time_total_minutes / 60) × human_hourly_rate_eur
benefit_yearly_eur = (immediate_gain_eur ou immediate_benefit × 100)
                   + (monthly_gain_eur ou monthly_benefit × 50) × 12
roi_ratio = benefit_yearly_eur / max(invest_eur, 1)
```

Quand `*_gain_eur` est renseigné, il prime sur l'échelle 1-5. Si seul le
1-5 est connu, un facteur conventionnel s'applique (100 €/point immédiat,
50 €/point/mois récurrent — ajustable dans `pm.pricing.yml` plus tard).

### Hook vs script manuel

- **Hook automatique** : sessions Claude Code (~/.claude/settings.json),
  attribution silencieuse en arrière-plan
- **Script manuel** : `scripts/pm-task-tick.py --rm-id X --tokens-input N --tokens-output N --model M --human-minutes M`
  pour les agents non-Claude-Code (n8n, scripts custom) ou ajout manuel de
  temps humain post-hoc

### Notes

- **Race conditions multi-sessions** : 2 Claude bossant sur le même ticket
  simultanément écrivent dans le même frontmatter — l'optimistic locking
  (`updated`) doit faire son job. Vérifier en pratique.
- **Cache reads** : ~10× moins chers que input pur — bien distinguer dans
  le calcul (cf. tableau `pm.pricing.yml`).
- **Précision** : la mesure ne prend en compte que les sessions Claude Code
  hookées. Sessions oubliées (sans hook) ou autres agents (n8n) → invisibles.

### Documentation dans Redmine — champs dédiés (obligatoire) — v1.21.0

Le frontmatter MD n'est pas suffisant : l'estimation et les cumuls doivent
être **visibles côté Redmine** dans les champs dédiés de l'instance (IDs à
revalider via le § « Synchronisation de la configuration Redmine »).

**Estimation prévisionnelle → poussée sur le ticket :**

| Frontmatter | Champ Redmine |
|---|---|
| `estimate.tokens` | CF **21** `Tokens prévus` (int) |
| `estimate.ai_time_minutes` (÷ 60) | CF **22** `Temps estimé IA (h)` (float) |
| `estimate.human_time_minutes` (÷ 60) | natif `estimated_hours` (temps estimé) |

**Quand estimer / réestimer** :
- **À la création** de la tâche (`pm-task-add`) : estimation initiale obligatoire,
  poussée immédiatement sur CF 21 / 22 / `estimated_hours`.
- **À la prise de ticket** (passage `en_cours`) : si aucune estimation n'a été
  faite auparavant (ticket créé hors PM, ou estimation oubliée), **l'établir à ce
  moment** — filet de sécurité avant de commencer le travail.
- **À la mise à jour de la description** : réestimer **uniquement si** le changement
  est assez conséquent pour impacter le temps/tokens prévu (sinon ne pas toucher).
  Tracer la réestimation dans le `.log.md` (ancienne → nouvelle valeur).

**Cumul effectif → poussé sur le ticket :** CF **17** `Tokens passés` reflète
`tokens_total` du frontmatter (recalé à chaque mise à jour Redmine).

### Journalisation par commit — temps + tokens consommés (obligatoire) — v1.21.0, convention activités + outillage v1.26.0

Le hook `pm-task-tick` (déclenché à chaque fin de réponse Claude) reste
**nécessaire** : il mesure et accumule en continu tokens + temps IA dans le
frontmatter MD — c'est la **base de calcul**. Le commit en est le **point de
report** vers Redmine.

**Règle** : à chaque commit **de travail** (unité = l'étape significative, cf. §
« Unité de traçabilité »), reporter sur le ticket Redmine le **delta** consommé
depuis le commit précédent, sous forme d'une **saisie de temps**
(`POST /time_entries.json`) :

- `issue_id` = le ticket ; `spent_on` = date du commit
- `hours` = temps IA wall-clock écoulé depuis le dernier commit (delta de
  `ai_time_total_minutes` ÷ 60). `hours=0` est **accepté** par l'instance —
  une étape sans temps mesuré reste donc une saisie datée valide (le tokens du
  delta, lui, est toujours porté par le CF 16).
- `activity_id` = **nature** du travail, dérivée du `type` de la tâche selon la
  **convention canonique ci-dessous** (≠ le tracker, qui encode la *catégorie*
  de ticket). Résolution outillée : `redmine_utils.activity_for_type(type)`.
- CF **16** `Tokens` = tokens consommés depuis le dernier commit (delta de
  `tokens_total`)
- commentaire = le hash + sujet du commit (lien `git.*`)

**Convention `type` de tâche → activité de temps Redmine** (source unique :
`redmine.reference.yml :: type_to_activity` ; surchargagle par saisie via
`pm-task-report.py --activity <id>`) :

| `type` NORMS | Activité Redmine | id | Nature |
|---|---|---|---|
| `feature` | `Developpement/Feature` | 31 | écrire une fonctionnalité neuve |
| `bugfix` | `Développement/Debug` | 16 | corriger un défaut |
| `maintenance` | `Développement/Refacto/Clean` | 30 | refacto, nettoyage, entretien |
| `infrastructure` | `SysAdmin/Conf/Debug` | 13 | déploiement, conteneurs, systemd, conf |
| `configuration` | `SysAdmin/Conf/Debug` | 13 | paramétrage applicatif / système |
| `research` | `Audit/Analyse` | 10 | investigation, audit, exploration |
| `assistance` | `Assistance` | 11 | aide / support ponctuel |
| `autre` | `Autre` | 18 | fourre-tout (défaut de repli) |

> La résolution se fait au grain **tâche** (par son `type`). La refacto ou la
> feature qui vit *dans* un commit d'un ticket d'un autre type ne sera taguée
> finement qu'avec le futur **mode incrémental par commit**, où chaque commit
> pourra déclarer sa propre nature (override `--activity` en attendant).

Après le report, le CF **17** `Tokens passés` du ticket est resynchronisé sur
le cumul, et l'entrée est tracée dans le `.log.md` (cf. § « Référencer un commit »).

**Note Redmine accompagnante.** Ces métriques (temps + tokens du delta) sont
reprises dans la **note Redmine** du commit, aux côtés du résumé détaillé et de
la réf du commit. Le *quand* et le *quoi* de cette note sont définis **une seule
fois**, dans la matrice canonique § « Unité de traçabilité : l'étape
significative » — ne pas les redéfinir ici.

**Outillage : `scripts/pm-task-report.py`** (RM1819). Lit le frontmatter +
`.log.md` d'un ticket (`--rm-id`) ou de tous (`--all`), et pousse vers Redmine :
une **time_entry datée par entrée `Tokens :` du log** (`spent_on`, `hours` =
temps IA, CF 16 = tokens, `activity_id` selon la convention ci-dessus,
comments = titre de l'entrée), puis **resync CF 17** = `tokens_total`.
Idempotent : le `time_entry.id` de chaque saisie est historisé dans le bloc
`reporting.time_entries[]` du frontmatter (clé de dédup `<ts>#<tokens>`), un
re-run ne crée pas de doublon. Dry-run par défaut, `--apply` pour exécuter.

> **Reste à outiller (gap résiduel)** : le déclenchement **automatique au
> commit** (hook `post-commit` calculant le delta depuis le dernier report).
> Aujourd'hui `pm-task-report.py` se lance à la main / par lot. Le mode
> incrémental fin (un time_entry par commit, avec nature de travail déclarée
> par commit) viendra dessus.

> 📂 **Module `task-links` — quand lire ceci :** je lie / fais dépendre / parente deux tickets.
> **Outils :** `pm-task-link` · **Préchargé par :** —.

## Liens entre tâches

Le frontmatter d'une tâche supporte plusieurs types de liens, chacun avec une
sémantique propre. Ces champs sont **symétrisés** (RM-id miroir maintenu côté
cible) et synchronisés avec les `relations` Redmine via le script
`scripts/pm-task-link.py`.

| Champ | Cardinalité | Sémantique | Miroir côté cible | Redmine `relation_type` |
|---|---|---|---|---|
| `parent_task` | `int \| null` | Hiérarchie : ce ticket a un parent | `sub_tasks` (attribut `parent_issue_id`) | — (attribut d'issue) |
| `sub_tasks` | `list[int]` | Hiérarchie : enfants directs | `parent_task` (attribut `parent_issue_id`) | — (attribut d'issue) |
| `depends_on` | `list[int]` | Bloquant : A doit attendre B (B finit avant A) | `blocks` côté B | POST sur B : `blocks` → A |
| `blocks` | `list[int]` | Bloquant : A doit finir avant B (réciproque de `depends_on`) | `depends_on` côté B | POST sur A : `blocks` → B |
| `relates` | `list[int]` | **Lien latéral non-bloquant** : sujet/famille commun | `relates` côté cible | POST `relates` |
| `refs` | `list[obj]` | Référence externe libre (URL, commit, ticket partenaire) | — | — (champ libre, pas de relation Redmine) |

### `refs: partner_issue` — ticket d'un gestionnaire partenaire (v1.69.0)

Quand un projet déclare un **provider secondaire** (gestionnaire de tâches d'un client
ou d'un prestataire, cf. `providers.task[]` du `meta.yml` — RM2653), un ticket PM peut
être **rattaché** à un ticket de ce gestionnaire. Le lien est un item `refs[]` typé :

```yaml
refs:
  - type: partner_issue
    instance: redmine-matnat      # DOIT être un secondaire déclaré du projet
    issue_id: 1234
    url: https://tasks.materiaux-naturels.fr/issues/1234
    role: mirror                  # mirror | upstream | related
    last_seen_journal_id: null    # pointeur de synchro, PAR LIEN
    added: 2026-08-12
```

| `role` | Sens |
|---|---|
| `mirror` | ce ticket **est** le mien vu de chez eux (1↔1) — **un seul** par tâche |
| `upstream` | leur ticket est la demande d'origine |
| `related` | voisinage : plusieurs de leurs tickets peuvent toucher la même tâche |

**Règles.** Le lien se pose **toujours** avec `pm-task-partner` (tripwire #1), jamais à
la main : l'outil valide que l'instance est un secondaire déclaré, refuse un doublon
`(instance, issue_id)` ou un second `mirror`, pose le CF Redmine « Ticket partenaire »,
journalise, et poste la note de rattachement chez le partenaire.

**Le partenaire ne décide de rien chez nous** : un `partner_issue` ne modifie **aucun**
champ du frontmatter (statut, priorité, assignation). Le provider **primaire** reste la
seule source de vérité ; ce qui vient d'un secondaire s'écrit dans le `.log.md`.

Quand le secondaire porte `link.policy: required` (« tout ce que je fais pour eux doit
être rattaché chez eux »), `pm-doctor` signale chaque ticket **ouvert** sans lien.

**Importer ce qui se dit chez eux** (v1.69.0) : `pm-task-partner pull <RM-id>` (ou
`--all`, câblable en cron) lit le ticket distant et **appende au `.log.md`** les notes
nouvelles — citées, sous un en-tête qui nomme l'instance — et leur statut **brut**
(leur libellé, pas un état NORMS). Réglable par secondaire via
`sync.pull: {notes, status}`. Le pointeur de lecture (`last_seen_journal_id`) vit **dans
le lien**, jamais dans `redmine_last_journal_id` qui suit l'instance primaire — deux
boucles, deux pointeurs. Un partenaire injoignable produit un avertissement, jamais un
échec : le PM ne dépend pas de la disponibilité d'un tiers.

**Rendre compte chez eux** (v1.69.0) : une transition de statut poste une **note de
suivi** chez le partenaire — **seulement** si le secondaire déclare ce statut dans
`sync.push.on`. **Défaut : rien ne part.** L'activation se fait projet par projet, après
revue du gabarit : une note poussée chez un tiers ne se rattrape pas.

* **Écriture pauvre** : une note de texte, jamais un statut, un champ personnalisé ni une
  saisie de temps — les ids de `redmine.reference.yml` sont ceux d'iProspective.
* **Gabarit fermé** : identifiant de suivi, titre, état **en clair**
  (`a_tester_demandeur` → « livré, en attente de validation » : le partenaire ne connaît
  pas notre machine d'états), plus un message rédigé à la main. Pas de chemin, d'hôte, de
  branche, d'environnement de test, ni d'URL interne — notre Redmine ne lui est pas
  accessible de toute façon.
* Le push est **best-effort** : il n'échoue jamais une transition déjà écrite côté PM.
* `pm-task-partner link --create-remote` crée le ticket manquant chez eux puis le
  rattache ; il exige un `create.tracker_id` déclaré (les ids de tracker ne sont pas
  portables — on ne devine pas).

**Règles d'intégrité :**
- Tout lien `relates` / `depends_on` / `blocks` doit avoir son miroir côté cible.
  Si l'un est présent sans l'autre, c'est un drift à corriger via
  `pm-task-link sync <rm-id>`.
- `parent_task` est unique (au plus un parent par tâche).
- Un ticket ne peut pas se lier à lui-même.
- `pm-task-link rm` supprime les deux côtés.

**Sens des dépendances** : ne pas confondre. Si **A dépend de B**, alors
`A.depends_on = [B]` ET `B.blocks = [A]`. Côté Redmine, c'est une seule
relation `blocks` postée depuis B vers A.

### Hiérarchie parent/enfant (v1.20.3)

`parent_task` / `sub_tasks` ne sont **pas des relations Redmine** mais l'**attribut
natif d'issue `parent_issue_id`** (colonne « Redmine `relation_type` » = `—` dans le
tableau). Ils ne transitent donc pas par `/issues/<id>/relations.json` mais par un
`PUT parent_issue_id` sur l'enfant. La réflexion MD ↔ Redmine est outillée — **ne jamais
éditer ces champs à la main** :

| Geste | Commande | Effet |
|---|---|---|
| Créer un ticket enfant | `pm-task-add … --parent <RM>` | POST avec `parent_issue_id` + `parent_task` enfant + `sub_tasks` parent |
| (Re)poser / déplacer le parent d'un ticket existant | `pm-task-link parent <child> <parent>` | PUT Redmine + migre `sub_tasks` ancien→nouveau parent |
| Détacher | `pm-task-link parent <child> --unset` | PUT Redmine (parent vidé) + retire de `sub_tasks` du parent |
| Réconcilier depuis Redmine | `pm-task-sync <RM>` | lit `issue.parent.id` → `parent_task` + maintient les `sub_tasks` locaux |

Le cœur (réflexion frontmatter des deux côtés + logs) vit dans `scripts/pm_hierarchy.py`,
partagé par les trois scripts. Quand le parent n'est pas tracké localement (ticket
Redmine hors-PM), le champ enfant est posé mais `sub_tasks` n'est pas maintenu (no-op
silencieux, le lien Redmine reste correct).

**Règles d'intégrité hiérarchie :**
- `parent_task` est unique (au plus un parent par tâche).
- Pas d'auto-parent ni de cycle (Redmine refuse les cycles au PUT ; les scripts
  refusent l'auto-parent en amont).
- `sub_tasks` est dérivé : il doit toujours refléter l'ensemble des enfants dont le
  `parent_task` pointe vers ce ticket. En cas de drift, `pm-task-sync` sur l'enfant
  rétablit la cohérence.

> 📂 **Module `traceability` — quand lire ceci :** je commit / franchis une étape significative · je journalise une décision · je référence un commit.
> **Outils :** `pm-task-report` · **Préchargé par :** —.

#### Journalisation des échanges avec l'humain (obligatoire, au fil de l'eau)

Quand un échange utilisateur ↔ agent porte sur une tâche — arbitrage, décision,
re-cadrage du besoin, retour de test, correction de cap — l'agent **résume** cet
échange et l'appende au `.log.md` de la tâche **au fur et à mesure**, sans attendre
la clôture. On journalise le *pourquoi* des décisions, pas seulement le code produit.

- **Résumer, pas recopier** : une synthèse pertinente, pas le transcript verbatim.
- **Au fil de l'eau** : une entrée par étape significative, datée. Objectif :
  pouvoir reconstituer le fil de la tâche (et les raisons des choix) sans relire
  la conversation d'origine.
- N'enregistrer que ce qui est lié à la tâche ; le bavardage hors-sujet n'a pas
  sa place dans le journal.

#### Traces mécaniques templatées — RM2365 (CDC RM2316 § S4)

Les notes Redmine des **événements mécaniques** sont générées par l'outillage
depuis `templates/notes/` (ex. `status_change.md` : ancien → nouveau statut,
assignation, branche/MR) — **l'agent ne rédige plus cette partie**. La règle :

- **Transition de statut** : ne passer `--note` à `pm-task-status-update` /
  `pm-task-take` / `pm-task-deliver` **que pour un ajout sémantique** (décision,
  contexte, résumé de livraison) — jamais pour paraphraser la transition,
  l'assignation, la branche ou la MR (le template les porte déjà).
- Les événements déjà journalisés ailleurs **n'appellent pas de note
  supplémentaire** : estimation (CF 21/22 visibles sur le ticket), liens
  (journal Redmine natif des relations), tick/report (déjà templatés).
- Le **sémantique reste obligatoire** là où il l'a toujours été : prise en
  charge avec plan, décisions/arbitrages, blocages, livraison (le
  `--summary` de `pm-task-deliver`).

#### Unité de traçabilité : l'étape significative (canonique) — v1.23.0

**Référence unique** pour « quand commiter, quand noter ». L'unité de travail
tracée n'est ni le fichier ni la frappe : c'est l'**étape significative** — un
incrément consistant et cohérent (livraison, fonctionnalité, correctif, décision
structurante). On ne commit ni chaque fichier sauvé, ni un seul gros bloc à la
toute fin : on commit **à la frontière d'une étape significative**.

À cette frontière, à partir d'**un seul effort de fond** décliné en deux
granularités, l'agent produit :

1. **Message de commit** — résumé **court** (1 ligne + corps optionnel), langue du repo.
2. **Note Redmine** — résumé **détaillé**, human-readable, destiné au ticket : ce
   qui a été fait/livré et *pourquoi*, + **réf du commit** (SHA + URL GitLab, cf.
   « Référencer un commit ») + **temps + tokens** du delta (cf. § « Journalisation
   par commit »). C'est la trace que les humains lisent — donc **aérée** : sauts
   de ligne aux ruptures d'idée plutôt qu'un unique bloc compact, sans pour
   autant sur-formatter une note de trois phrases (pas de titres/listes à
   outrance).
3. **Entrée `.log.md`** — variante technique de l'agent (détail, décisions) + réf
   commit + métriques, append-only (format ci-dessus). Les humains ne la lisent pas.
4. Si l'étape est une **livraison** : transition de statut + `done_ratio` au même
   moment (cf. §§ dédiés).

> Même synthèse de fond, supports différents (long → note, court → commit,
> technique → log) : pas trois rédactions distinctes.

**Quand poster une note Redmine** — matrice unique, ne pas redéfinir ailleurs :

| Événement | Note ? |
|---|---|
| Commit de **travail / livraison / structurant** (chose dont on veut garder trace) | **Oui** — note détaillée + réf commit + métriques |
| Événement **structurant sans commit** (cahier des charges, réflexion, arbitrage, décision, re-cadrage) | **Oui** — note complémentaire (synthèse, sans réf commit) |
| Commit **trivial / housekeeping** (sync frontmatter, append `.log.md`, fix typo doc PM) | **Non** (sauf `commit_note_level: all`) |
| Simple changement de **statut** ou `done_ratio` | **Non** — Redmine les journalise nativement |
| Mise à jour de **description** (texte/checklist) | **Oui** — cf. § « Mise à jour de la description » (Redmine ne diff pas les descriptions) |

**Niveau de note par commit — configurable** (`pm.config.yml :: traceability.commit_note_level`,
pour calibrer le bruit à l'usage) :
- `work` (défaut) — note pour les commits de travail/livraison/structurants uniquement.
  Concrètement (RM2409) : les commits d'**outillage** — sujet préfixé `pm(<verbe>):`
  (auto-commits des scripts `pm-*`) ou `chore(…):` — reportent la conso **sans note** ;
  tout autre commit rattaché à une tâche est co-posté en note avec sa réf `— commit sha`.
- `all` — note pour **tout** commit rattaché à une tâche (mode test : mesurer le bruit réel).
- `none` — pas de note auto par commit (on conserve `.log.md` + time_entry).

**Override par projet** : `meta.yml` du projet (dossier `.mmi-pm`) peut porter la même
clé `traceability: { commit_note_level: … }` — priorité : projet > `pm.config.local.yml`
> `pm.config.yml` > défaut `work`. Appliqué par le hook `pm-post-commit`.

#### Référencer un commit dans une entrée

Toute entrée de journal qui **produit ou modifie du code** doit citer le(s)
commit(s) correspondant(s), pour tracer précisément quelle livraison à quelle étape :

```markdown
Commit: <repo-alias>@<sha-court> — <message court>
        https://gitlab.iprospective.fr/<ns>/<repo>/-/commit/<sha-complet>
```

- La forme **canonique de tracking** est le SHA (≥ 7 caractères) ou, mieux quand le
  repo est sur GitLab, l'**URL de commit complète** (cliquable et résolvable).
- Le frontmatter `git.branch` / `git.mr_url` reste le pointeur *courant* (branche de
  travail, MR ouverte) ; le `.log.md` conserve l'*historique* des commits par étape.
  Pour une référence ponctuelle hors workflow dev, utiliser `refs: [{type: commit, …}]`.
- **Prérequis** : le workspace doit être un dépôt git. S'il ne l'est pas (ex. un
  workspace infra non initialisé), il n'y a pas de commit à référencer — le signaler
  explicitement dans l'entrée plutôt que de laisser un trou.

---

> 📂 **Module `environments` — quand lire ceci :** je me connecte à / référence un environnement · je manipule un secret (vault, quel qu'il soit).
> **Outils :** `ssh_alias`, `resolve-secret.sh` · **Préchargé par :** worker-dev, worker-infra.

### Environnements (aspect `environments.md`)

Aspect dédié à la déclaration des environnements d'exécution d'un projet (dev, test,
staging, prod, etc.), distinct de `hosting.md` (provider/coûts/DNS).

**Format** : frontmatter avec liste `environments[]`, chaque entrée décrivant un env.
Voir `templates/aspects/common/environments.md`.

**Format des entrées** — noms d'env admis, champs (`ssh_alias`, `post_deploy`,
`logs.*`, `env_vars[]`…) et conventions de chemins : `modules/environments-reference.md`
(hors précharge, ouvert quand on écrit l'aspect).

**Connexion SSH (règle d'usage)** : pour se connecter à un env, utiliser **`ssh_alias`
s'il est renseigné** (il porte les `ProxyJump`/clés de `~/.ssh/config` — cf. convention
OVH « alias = nom du conteneur »), **sinon `ssh_target`** (`user@hostname` explicite).
`host`/`user` restent indicatifs (préfixe des logs distants, contexte) et ne sont pas la
commande de connexion.

**Cascade** : un `environments.md` peut exister au niveau client (conventions par défaut
sur l'host, user, secrets_source) et au niveau projet (surcharge ou complète).

**Lien avec les tâches** : le frontmatter de tâche peut référencer un env via
`target_env: <name>`. Si présent, `test_url` se déduit de `environments.<target_env>.url`
(sauf si `test_url` est explicitement surchargé). Pour les **envs de session par
ticket** (RM1834), `pm-env-session` tient `test_url` à jour tout seul : `create`
écrit `http://<repo>-rm<id>.lxc/` (frontmatter + CF « Environnement de test »),
`teardown` les **vide** — ne jamais laisser une URL morte affichée (RM2229).

> **Résolution du worktree : PAR BRANCHE, jamais par chemin deviné (RM2394).**
> Le vhost et l'`env_name` restent l'**identité stable** du ticket
> (`<repo>-rm<id>.lxc`), mais le **worktree** est trouvé via sa branche `<id>-*`
> (`git worktree list`), quel que soit le nom du dossier : canonique
> `envs/<repo>-rm<id>` **ou** discriminé par session `envs/<repo>-dev-<id>-s<seq>`
> (RM2034), **ou** renommé/créé à la main. C'est la seule convention qui survit au
> multi-session et aux `git worktree move` — l'alternative (forcer un nom canonique
> à la création) casserait la discrimination RM2034. Conséquence : `pm-env-session
> create` et `pm-cockpit-test-env create` **réutilisent** le worktree déjà monté
> (pris avec `pm-branch-start --worktree`) et posent le vhost/runtime **par-dessus**
> (idempotent, le helper réécrit le `DocumentRoot`), au lieu d'échouer en `rc=128`.
> Résolveur partagé : `pm-env-session.worktree_for_branch()`.


### Gestion des secrets — vaults déclarés

Les credentials sensibles (mots de passe, tokens, clés) **ne sont jamais commités**,
ni dans le repo PM public, ni dans le repo projets privé. Ils vivent dans un
**gestionnaire de secrets** et sont **référencés** dans les documents PM par un URI.

**Plusieurs vaults peuvent coexister** (RM2662) : chacun est une **instance** déclarée
dans le registre providers (`pm.config.yml :: providers.servers`, axe `secret`), nommée
par un slug, avec un défaut et une surcharge possible **par client ou par projet**.

```yaml
providers:
  defaults:
    secret: vw-ipro                 # vault par défaut
  servers:
    vw-ipro:     { axis: secret, type: vaultwarden, url: "${VAULT_URL:-…}" }
    kdbx-perso:  { axis: secret, type: keepass, file: "~/vaults/ipro.kdbx" }
    age-acme:    { axis: secret, type: age, file: "~/vaults/acme.yml.age" }
    op-ipro:     { axis: secret, type: onepassword, vault: "Agents" }
```

**Aucun secret dans cette déclaration** : URLs, types et chemins seulement. Les
identifiants d'accès sont **par développeur**, dans `~/.config/mmi-pm/.env`, nommés
par slug **normalisé** (majuscules, non-alphanum → `_`) :
`SECRET__VW_IPRO__CLIENTID`, `SECRET__KDBX_PERSO__FILE`, `…__TOKEN`.

**URI — trois formes, toutes valides :**
```
secret://<instance>/<chemin…>[#champ]      instance nommée explicitement
secret:<chemin…>[#champ]                   instance par défaut (cascade projet/client)
vaultwarden://<org>/<collection>/<item>    forme historique — supportée définitivement
```

Ex : `secret://vw-ipro/calicote-agents/prod-db`, ou
`vaultwarden://iprospective/calicote-agents/prod-db` (équivalent, jamais à réécrire).

**Backends disponibles** : `vaultwarden` (défaut), `keepass` (`.kdbx`, dép.
`python3-pykeepass`), `age` (fichier YAML/JSON chiffré, dép. `age` — « on me partage
trois identifiants », sans serveur ni compte), `nextcloud_passwords` (app **Passwords**
d'un Nextcloud, mot de passe d'**application**) et `onepassword` (CLI `op` + *service
account* ; CLI hors dépôts Debian, jeton machine sur plan payant). D'autres s'ajoutent
par `pm_secrets.register_backend()` sans toucher aux appelants.

**Un secret chiffré côté client est refusé, pas rendu.** Quand l'app Passwords chiffre
un item avec une clé que seul le navigateur détient, l'API n'en rend qu'un cryptogramme :
le backend REFUSE (`unsupported`, en nommant le chiffrement) plutôt que de livrer une
valeur qu'un agent injecterait dans une conf en la prenant pour un mot de passe. Donc :
un secret destiné aux agents ne se pose pas dans le périmètre chiffré côté client.

**Tous les vaults ne se déverrouillent pas.** Un fichier `age` s'ouvre avec une clé
privée posée sur le poste ; un accès par jeton (service account 1Password, mot de passe
d'application Nextcloud) tient par ce jeton : **pas de session à établir**, donc pas de
secret humain à saisir. Deux conséquences. Ces vaults **ne se verrouillent pas** —
`lock-vault.sh` n'agit que sur les sessions gardées en mémoire. Et leur refus ne
s'ouvre pas : un jeton refusé se rapporte `locked`, faute d'une quatrième valeur au
contrat, mais il faut en **émettre un nouveau**, pas chercher un mot de passe maître
qui n'existe pas. Pour `age`, **seuls les droits du fichier protègent le vault** : clé
en `0600` (`SECRET__<SLUG>__AGE_KEY_FILE`), jamais commitée, jamais dans la déclaration
partagée — la page de santé du poste signale une clé trop ouverte.

**Un secret ne passe jamais en argument de commande** : `ps` est lisible par tous les
processus de la machine, et le shell en garde l'historique. Il se transmet par variable
d'environnement ou sur l'entrée standard (`unlock-vault.sh --stdin`).

> **Secrets d'un client : la collection `<client>-agents` d'abord.** Déclarer une
> instance dédiée sert aux **intervenants** qui ont leur propre outil, ou à un client
> qui **impose** son gestionnaire. Pour les secrets d'un client hébergés chez nous, la
> voie normale reste une collection `-agents` du vault iProspective (ci-dessous).

**Architecture du vault par défaut** (chez iprospective) :

```
Organization iProspective
├── <client>            ← collections existantes, accès Mathieu uniquement
├── <client>-agents     ← sous-scope pour les items que les agents peuvent lire
│   └── membre : karl@iprospective.fr (User, Read-only)
└── iprospective-agents ← idem pour les secrets internes (Redmine bot, n8n, etc.)
    └── membre : karl@iprospective.fr (User, Read-only)
```

- Un seul user d'agents : `karl@iprospective.fr` (alias technique unique)
- Scope **read-only** sur les collections `*-agents` uniquement
- Les credentials critiques (root SSH, BDD admin, master gitlab, etc.) restent en
  dehors du scope agents

**Cycle de vie des sessions :**

| Action | Outil | Acteur |
|---|---|---|
| Déverrouillage | `scripts/unlock-vault.sh [-i <instance>]` (demande le secret humain — master password ou passphrase —, jamais stocké) ou, dans le **cockpit**, le bouton **🔓 déverrouiller** de l'en-tête, qui n'apparaît que si un coffre est fermé (RM2748). Sur un vault **sans session** (ex. `age`), il n'y a rien à déverrouiller : la commande ne fait que diagnostiquer l'accès | toi (humain) |
| Résolution d'un secret | `scripts/resolve-secret.sh "<uri>" [champ]` | agent / script |
| Verrouillage manuel | `scripts/lock-vault.sh [<instance>]` | toi |
| Inventaire d'un vault | `scripts/vault-list.sh [-i <instance>] [filtre]` | toi / agent |
| Quel vault pour ce projet ? | `scripts/pm-providers.py resolve secret` | toi / agent |

Le déverrouillage démarre un daemon local `vault-agentd.py` qui :
- garde **une session par instance**, **en mémoire** uniquement (pas de fichier, pas
  même tmpfs) — déverrouiller le vault d'un client ne prolonge pas celui d'iProspective
- expose un socket Unix `/run/user/$UID/vault-agentd.sock` (chmod 600)
- verrouille **chaque instance** après inactivité (`VAULT_IDLE_TIMEOUT`, défaut 8h)
  et/ou à une heure fixe (`VAULT_LOCK_AT_HOUR`, défaut 23h), et ne s'arrête que
  lorsqu'il ne reste plus aucune instance ouverte

**Règles strictes :**
1. Un agent ne demande **jamais** le secret de déverrouillage (master password,
   passphrase) ; si `resolve-secret.sh` sort en code 2, l'agent dit à l'humain « lance
   `unlock-vault.sh`, ou déverrouille depuis le cockpit » et attend. Le mode non
   interactif (`--stdin`) existe pour un appelant qui **transmet** un secret déjà saisi
   par l'humain (le cockpit) — jamais pour qu'un agent en fabrique ou en réutilise un.
   Un code 4 `unreachable` n'est PAS un verrou : c'est une configuration ou une
   dépendance manquante — le message dit laquelle
2. Les secrets résolus **ne sont jamais loggués**, jamais écrits sur disque, jamais
   inclus dans un commit ou un transcript. Un diagnostic peut nommer les **clés**
   d'identifiants trouvées, jamais leurs valeurs
3. La rotation des identifiants d'agent est trimestrielle (ou immédiate en cas de doute)
4. Les agents 24/7 (cron nocturne, n8n) ne peuvent fonctionner que dans la fenêtre
   d'unlock manuel ou via un sous-scope dédié explicitement autorisé (cas particulier)
5. Un URI visant une **instance inconnue** est refusé, jamais rabattu sur le vault par
   défaut — chercher un secret dans le mauvais coffre est l'erreur silencieuse à éviter

**Identifiants** — par dev, dans `~/.config/mmi-pm/.env`, nommés par slug d'instance
(`SECRET__<SLUG>__…`). Les variables historiques `VAULT_URL` / `BW_CLIENTID` /
`BW_CLIENTSECRET` restent lues en repli tant qu'un dev n'a pas migré.

**Convention dans `environments.md` et autres aspects** : utiliser
`secrets_source: secret://<instance>/<chemin>` (ou la forme historique
`vaultwarden://…`, toujours valide) comme pointeur, jamais la valeur brute. Documenter
dans `client/security.md` (ou équivalent) la liste des items référencés et leur rôle,
pour audit humain.

> 📂 **Module `environments-reference` — quand lire ceci :** j'écris ou j'édite un aspect `environments.md` · je cherche le nom exact d'un champ d'environnement · je déclare un `post_deploy` ou un chemin de logs.
> **Outils :** `templates/aspects/common/environments.md` · **Préchargé par :** *(personne — ouvert à la demande)*.

# Environnements — format de l'aspect (référence)

Détaché de `environments.md` par RM2755 : ces sections décrivent la **forme** du
fichier d'aspect — noms d'env admis, champs, conventions de chemins. On les ouvre
quand on ÉCRIT un `environments.md`, pas à chaque tâche. Les **règles d'usage**
(quelle commande de connexion, cascade, `target_env`, secrets) restent dans
`environments.md`, préchargé.

### Noms et champs

**Énumération des noms d'env standard :**
`local | dev | test | staging | prod | demo | qa | sandbox | <nom-custom-kebab-case>`

> **`staging` et `preprod` sont un seul et même environnement** (fusionnés en v1.36.0) :
> l'env de non-régression avant prod, déployé depuis **`preprod_branch`** quand le projet
> est en **flux 3 branches** (opt-in, RM2030), **sinon** depuis `integration_branch`
> (modèle 2 branches). **Valeur
> canonique = `staging`** ; `preprod` reste accepté comme **alias** (le statut Redmine
> id 20 s'appelle toujours « MEP/Tester en preprod » et le narratif MEP ci-dessous parle
> de « preprod » — c'est le même env que `staging`). Ne pas déclarer deux entrées
> distinctes pour ce rôle.

Custom autorisé si le projet a une particularité (ex: `staging-eu`, `staging-archive`,
`prod-canary`).

**Champs par environnement :**
- `name` (obligatoire, enum ci-dessus)
- `status` : `active | disabled | planned`
- `url`, `admin_url` : URLs publiques/admin
- `ssh_alias` : **alias SSH** `~/.ssh/config` (avec `ProxyJump`/`HostName`/`User`/clés
  préconfigurés), **à utiliser de préférence** pour toute connexion. Ex: `calicote-presta`.
- `ssh_target` : **cible SSH explicite** `user@hostname` (fallback quand aucun alias
  n'est défini). Ex: `calicote@srv1.sfy-gestion.com`.
- `host`, `user`, `app_path`, `branch` : identité machine, user système, chemin du code,
  branche déployée
- `fpm_pool`, `logs.app`, `logs.fpm`, `logs.access` : observabilité
- `secrets_source` : pointeur vers un secret d'un vault déclaré (cf. section « Gestion des secrets »)
- `post_deploy` : **liste de commandes shell** à exécuter après un déploiement sur cet
  env (ex. purge du cache applicatif). C'est la forme **scriptée** de la procédure de
  déploiement, à préférer à la prose (la prose ne sert qu'à expliquer le *pourquoi*).
  Deux règles **impératives** :
  - **Déclaratif, NON auto-exécuté** : ce champ *documente* les commandes ; aucun outil
    ne les lance automatiquement pour l'instant. Un humain les exécute délibérément. Sur
    la prod, toute commande modifiant l'état exige le **consentement explicite** (cf.
    « Règle de sécurité prod »).
  - **Chemins ABSOLUS obligatoires** : ancrer chaque chemin sur `app_path`. Un
    `rm -rf var/cache/*` *relatif* vise `/var/cache` (dossier système Linux) s'il est
    lancé du mauvais cwd — écrire `rm -rf /home/<user>/public_html/var/cache/*`.
- `notes` : libre

### Conventions de chemins

**Logs (`logs.app` / `logs.fpm` / `logs.access`)** : chemins des logs, préfixés de
l'host si le fichier est sur une machine distante (`<host>:<path>`).
- `logs.app` : log applicatif (Symfony/PrestaShop, ex: `var/logs/prod.log`).
- `logs.fpm` : log du pool PHP-FPM (cf. § conventions FPM, ex: `/var/log/php/calicote-74.error.log`).
- `logs.access` : access log du serveur web. **Convention prod iProspective (OVH)** :
  un fichier par vhost sur le serveur hébergeur, à
  `/var/log/nginx/<domaine>_access.log` (+ `<domaine>_error.log`).
  Ex: `sfy-srv1:/var/log/nginx/calicote.com_access.log`. Utile pour analyser la charge
  de crawl (bots/scrapers), diagnostiquer des pics, ou auditer les accès.

**Tableau `env_vars[]`** : liste des variables d'environnement attendues (noms,
description, dans quels envs elles existent). **Sans les valeurs** — celles-ci sont
soit dans le `.env` local (gitignored), soit dans un vault via `secrets_source`.
> 📂 **Module `collaboration` — quand lire ceci :** je suis l'orchestrateur : rôles, assignation, sous-tâches multi-niveaux, propagation de complétion.
> **Outils :** — · **Préchargé par :** orchestrateur.

### Rôles des agents

**Orchestrateur**
- Un agent coordinateur unique par périmètre actif
- Surveille les tickets en attente (`a_faire`) dont les dépendances sont satisfaites
- Assigne les tickets aux workers via l'API Redmine (opération atomique)
- Seul écrivain sur les fichiers de tâches parentes (à tous les niveaux)
- Met à jour `completion_pct` des parents quand leurs enfants terminent (propagation bottom-up)
- Déclenche le testeur/reviewer quand une tâche passe en `a_tester_dev`
- Route les tickets vers le bon worker selon le champ `type`

**Workers (agents spécialisés)**

| Type de tâche | Agent |
|---|---|
| `feature` / `bugfix` / `refactoring` / `security` / `performance` | worker-dev |
| `audit` / `research` / `documentation` / `assistance` / `maintenance` | worker-analyst |
| `database` | worker-db |
| `infrastructure` / `configuration` | worker-infra |
| `design` | worker-design |

- Propriétaire exclusif de leur fichier de tâche assignée
- Lecture seule sur tous les autres fichiers MD
- Append-only sur tous les `.log.md`

**Reviewer**
- Déclenché par l'orchestrateur sur `a_tester_dev` (test indépendant, par un agent
  ≠ celui qui a fait le dev)
- Lit le fichier de tâche + le `.log.md` + les critères d'acceptation
- Valide → `a_tester_demandeur` (passe la main au demandeur ; ne clôt pas — la
  clôture passe par la validation demandeur puis la MEP, cf. § Cycle dev → MEP)
- Rejette → `a_corriger` avec note obligatoire dans le `.log.md`

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
8. Worker passe le ticket Redmine en a_tester_dev
9. Orchestrateur détecte le changement, déclenche le testeur/reviewer
10. Reviewer valide → a_tester_demandeur (puis demandeur → a_mep → MEP), ou renvoie en a_corriger
11. Si validé : orchestrateur propage la completion au parent
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

## Collaboration multi-agents

### Multi-utilisateur & concurrence — v2.0.0

Plusieurs devs (et leurs agents) travaillent **en même temps** sur les mêmes données communes
(arbo des tâches, dépôts `*-core`, docs). Le modèle mono-`karl` / *single-writer global* est
remplacé par *identité par dev + accès concurrent sérialisé par ressource*.

- **Identité par dev.** Secrets/config en cascade **`os.environ` > perso
  `~/.config/mmi-pm/.env` (`600`) > instance `pm.env` (non-secret) > commun `.env` (fallback
  karl)**. `--assign-to me` (et `en_cours`) = **dev humain courant**, pas un compte de service.
- **`karl` = persona / admin.** Ops privilégiées (prod `.mmi-pm-core` root-owned, branche
  **protégée**, tokens partagés, systemd/cron) via **`sudo` humain** — **pas de `karl-sudo`**.
- **Données communes en groupe `pm`.** Squelette `2750` (non group-writable, anti-déstructuration),
  churn (`.mmi-pm/`, `tasks/`, `docs/`, `envs/`) `2770`/`2775` setgid **jamais sticky** (sticky ⊥
  rename-overwrite atomique → `EPERM`), bares `core.sharedRepository=group` (commits multi-dev sans
  sudo). Contenu de travail (`envs/<ticket>`) = au créateur. Enforcement idempotent committé :
  **`pm-perms`**, jamais un runbook jetable.
- **Sérialisation par ressource.** `flock` par ticket (`var/locks/`) + écritures atomiques
  `os.replace` remplacent le single-writer ; contention = écriture **différée** bornée, pas rejetée ;
  crash-safe (`flock` libéré par le noyau ; FS local, pas NFS) ; `pm-lock-gc` (cron) nettoie les
  anomalies sans casser un verrou vivant. Le verrou optimiste `updated` reste l'arbitre
  **inter-machine**. Détail : tripwires du KERNEL (§ Propriété, verrou & journal).
> 📂 **Module `summarizer` — quand lire ceci :** je génère les fichiers auto-générés (Changelog / Pistes / Remarques).
> **Outils :** — · **Préchargé par :** summarizer.

## Fichiers auto-générés (écrits par l'agent summarizer)

| Fichier | Niveau | Contenu | Source |
|---|---|---|---|
| `Changelog.md` | client + projet | Activité datée (tâches fermées, étapes franchies) | Trigger événementiel sur `ferme` |
| `Pistes.md` | client + projet | Idées non décidées capitalisées | Agrège les `pistes[]` des tâches |
| `Remarques.md` | client + projet | Observations factuelles des agents (patterns, anomalies) | Extraits des `.log.md` |
| `client.md ## Structure` | client | Comment ce client opère, ses processus | Agrège observations long terme |
| `project.md ## Structure` | projet | Comment ce projet est architecturé, ses conventions | Agrège observations long terme |

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

Principe commun : **pas de rattrapage** (RM2250), pas de valeur qui rouille
(pointer `norms/VERSION`, `scripts/`, le command-catalog), niveau **jalon** et non
commit-par-commit (le détail vit dans les tickets).

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
