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
| je livre / teste / mets en preprod (MEP) | `modules/git-mep.md` + `modules/status-workflow.md` | `pm-task-status-update` |
| je change un statut de tâche | **tripwire #4** + `modules/status-workflow.md` | `pm-task-status-update` (`--list-next`) |
| je prends une tâche (passage en_cours) | **tripwire #5** + `modules/status-workflow.md` | `pm-task-status-update` |
| fin de dev / routing vers test | `modules/status-workflow.md` (`requires_agent_test`) | `pm-task-status-update` |
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
| je me connecte à / référence un environnement | `modules/environments.md` | `ssh_alias` |
| je manipule un secret / credential | **tripwire #11** + `modules/environments.md` | `resolve-secret.sh` |
| début de session PM : péremption des PAT GitLab | `modules/git-mep.md` (rotation J-7) | `pm-token-check` |
| je lie / fais dépendre / parente deux tickets | `modules/task-links.md` | `pm-task-link` |
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
3. **Branche par ticket + livraison par MR.** Coder un ticket = sur une branche `<RMid>-<slug>` tirée de la branche d'intégration (jamais directement dessus) ; renseigner le CF Redmine *GIT Branche*. **Livraison = Merge Request** sur le remote (jamais un merge poussé en direct sur l'intégration), et **la branche distante est CONSERVÉE** après merge (suppression d'une branche distante = accord explicite requis ; autoriser un merge ≠ autoriser une suppression). Ménage des branches mergées **uniquement en local**. **Aucun commit/push direct sur une branche protégée** — intégration (`dev`) **ET** prod (`main`/`master`) : tout passe par branche de ticket + MR, y compris la **promotion `dev`→prod** (modèle 3 branches). Un commit direct sur `main` court-circuite la promotion → divergences et collisions de version ; à **enforcer côté GitLab** (protection de branche : push direct interdit, seul le merge de MR autorisé). → `modules/git-mep.md`
4. **Sync statut MD↔Redmine.** Tout changement de `status` se répercute **dans le même cycle** : Redmine (status_id + note) + frontmatter (`status`, `status_history`, `updated`) + `.log.md`. **Toujours** via `pm-task-status-update.py`, **jamais** un statut « en dur » ; demande les cibles valides via `--list-next`. **Fermeture bloquée par sous-tâche ouverte** : un parent ne passe `ferme` que si **toutes ses sous-tâches sont elles-mêmes fermées** — sinon Redmine **refuse silencieusement** (PUT 204, statut inchangé, faux air de « permission *Edit issues* manquante »). Ne pas s'acharner ni conclure « droits » : vérifier `GET /issues/<id>.json?include=children` (et `allowed_statuses`). → `modules/status-workflow.md`
5. **Prise en charge ⇒ auto-assignation.** Passer une tâche en `en_cours` **implique**, dans le même mouvement, se l'**assigner** (`assigned_to`). Pas d'`en_cours` flottant. → `modules/status-workflow.md`
6. **redmine_id obligatoire.** Toute tâche/projet MD est reliée à son équivalent Redmine ; nom de fichier `RM{id}_…` cohérent avec `redmine_id`. → `modules/status-workflow.md`
7. **Filtrage IA.** Tout ticket créé depuis le système PM porte le CF `IA = "IA"` (posé par les outils au POST). Pas de MD local sans CF IA. → `modules/redmine-reference.md`
8. **Estimation.** Estimer (tokens + temps) **à la création** d'une tâche, et **à la prise** si l'estimation manque. → `modules/roi-pricing.md`
9. **Description vivante.** Si le ticket a une **checklist** ou un état décrit en prose : la tenir à jour **dans la description** (pas seulement en note), + `done_ratio` au fil de l'eau. → `modules/redmine-hygiene.md`
10. **Sécurité prod.** Aucune commande susceptible de modifier/casser la **production** sans **consentement humain explicite pour cette action précise**. Inspecter en lecture seule, proposer la commande exacte, attendre le feu vert ; un accord ne vaut pas pour l'étape suivante. → `modules/git-mep.md`
11. **Secrets.** Jamais commités, loggués, écrits sur disque ni dans un transcript ; jamais demander le master password Vaultwarden. → `modules/environments.md`
12. **Traçabilité par étape.** À chaque étape significative : commit + **note Redmine** (détail + réf commit + temps/tokens) + entrée `.log.md`. → `modules/traceability.md`
13. **Jamais d'identifiant séquentiel prédit — RM-id, iid de MR, ou autre.** Ne **jamais** saisir de mémoire un id issu d'une séquence partagée (« dernier vu + 1 ») : Redmine ET GitLab séquencent **globalement à l'instance** (plusieurs agents/projets créent en concurrence), le prochain numéro n'est **pas prévisible** (incidents : RM2142, RM2163, branche 2219→RM2222, merge de la MR !122 d'une autre session). **INTERDIT** (décision Mathieu 2026-07-11) : tout numéro se **capture de la sortie d'un script**, jamais ne s'infère. Outillage : `ID=$(pm-task-add … --porcelain)` ou `--start-branch` (atomique) ; `IID=$(pm-mr create … --porcelain)` ou `pm-mr create --merge` (atomique) ; `pm-mr merge --expect-rm <id>` (garde). Gardes automatiques : refus pm-mr sur branche divergente, hook git pre-push. → `modules/session-tooling.md`

Les tripwires **structurels** (propriété exclusive du fichier, optimistic locking, journal append-only) sont énoncés juste en dessous, suivis de la colonne vertébrale (cascade, nommage, schéma frontmatter, énumérations).

## Propriété, verrou & journal — tripwires structurels

### Principe fondamental

**Redmine est le mutex. Les fichiers MD sont le contexte de travail.**

L'assignation d'un ticket Redmine à un agent lui confère la **propriété exclusive** du fichier MD correspondant. Aucun autre agent ne doit écrire dans ce fichier tant que l'assignation est active.

L'inférence LLM est déjà distribuée par nature (appels API vers Anthropic). Ce qui doit être coordonné, c'est uniquement l'accès aux fichiers.

### Règles d'écriture

| Fichier | Orchestrateur | Worker assigné | Autres workers | Reviewer |
|---|---|---|---|---|
| `RM{id}.md` (tâche assignée) | lecture | **R+W** | lecture | lecture |
| `RM{id}.md` (tâche parente) | **R+W** | lecture | lecture | lecture |
| `RM{id}.log.md` | append | append | lecture | append |
| `project.md` | **R+W** | lecture | lecture | lecture |
| `NORMS.md` | lecture | lecture | lecture | lecture |

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

