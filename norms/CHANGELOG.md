# Changelog des normes

Toutes les évolutions notables sont documentées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/)

---

## [1.19.1] - 2026-06-01

### Clarifié — Procédure de mise à jour de NORMS anti-collision (multi-sessions)

Ajout d'une sous-section *Procédure de mise à jour* dans § « Versionning des normes ».
Avant de bumper la version **et** de committer, vérifier qu'aucune mise à jour
parallèle n'a déjà engagé le même numéro de version, sous deux formes : (1) **update
non commité** sur le filesystem partagé → relire `schema_version` sur disque juste
avant de choisir le numéro cible ; (2) **commit non pull** → `git fetch` + vérifier
que la branche n'est pas en retard (`pull --rebase` au besoin), résoudre les conflits
`schema_version`/`CHANGELOG` délibérément. Bump = dernière étape + commit immédiat.

---

## [1.19.0] - 2026-06-01

### Ajouté — Workflow test + mise en production (MEP) et statuts associés

Formalise dans NORMS le cycle dev → test → MEP déjà partiellement implémenté côté
Redmine. Mise en cohérence de la machine d'états avec les statuts existants de
l'instance (qui en avait plus que NORMS n'en mappait).

- **5 statuts** ajoutés/explicités, tous déjà présents côté Redmine :
  `a_tester_dev` (id 19), `a_tester_demandeur` (id 9, remplace `a_tester_verifier`),
  `a_mep` (Résolu/Validé/A MEP, id 3, **non terminal**), `en_mep` (MEP/Tester en
  preprod, id 20), `en_pause` (Attente retour / en pause, id 13).
- `a_tester_verifier` **déprécié** → alias en lecture de `a_tester_demandeur`.
- **Machine d'états** étendue (transitions dev → a_tester_dev → a_tester_demandeur →
  a_mep → en_mep → ferme ; en_pause depuis tout état actif) + mapping NORMS↔Redmine
  remis à jour.
- **Règles d'attribution** par transition complétées (testeur ≠ dev sur `a_tester_dev`,
  responsable MEP sur `a_mep`, testeur humain sur `en_mep`).
- **Nouvelle section canonique** *Cycle de développement → test → mise en production* :
  branches de référence par projet (bloc `git:` dans `overview.md` —
  `prod_branch`/`integration_branch`/`repo`/`remote`), modèle d'environnements
  (1 prod, 1 preprod, N test, N dev), workflow dev (branche `<RMid>-<desc>`, CF
  `GIT Branche` puis MR `branche→dev` tracée dans CF `GIT PR`) et workflow MEP
  (provisoire : preprod → vérif humaine → merge `dev`→prod + pull).
- **Section *Architecture de déploiement § V2*** réécrite : ne traite plus que de la
  distribution des agents ; le workflow de branches/release pointe vers la nouvelle
  section (suppression d'un cycle de vie contradictoire `agent/{server}/…` → `main`).

### À suivre (hors périmètre de cette version doc)

Mise à jour des **scripts et templates** pour enforcer le nouveau modèle :
`pm-task-status-update.py` (enum + map + normalisation de l'alias + création de
branche sur `en_cours` + gate checklist sur `a_tester_demandeur`/`a_mep`),
templates `overview.md` (bloc `git:`) et `bootstrap-tasks/005-deployment`. Tracké
dans un ticket dédié.

---

## [1.18.0] - 2026-06-01

### Ajouté — Branche de travail renseignée dans le CF Redmine « GIT Branche »

Complète la section § « Branche de travail par ticket » (v1.17.0).

- Dès la **création** d'une branche dédiée à un ticket, l'agent renseigne le
  **custom field Redmine `GIT Branche`** (id 3, string) avec le nom de la branche
  (et `GIT PR`, id 4, avec l'URL de la MR/PR une fois ouverte).
- C'est le CF dédié, **pas une note** : info visible et filtrable côté Redmine.
  Le frontmatter MD `git.branch` / `git.mr_url` reste le miroir local.

---

## [1.16.0] - 2026-05-26

### Ajouté — `% réalisé` (done_ratio) maintenu au fil de l'eau + outillage description

Étend la règle de mise à jour de la description (§ « Mise à jour de la description
du ticket Redmine »).

- L'agent maintient le **pourcentage de réalisation** (`done_ratio` Redmine ↔
  `completion_pct` MD) **au fur et à mesure**, dérivé du ratio de cases cochées de
  la checklist (par défaut) ou de son évaluation à défaut de checklist — pas
  seulement à la clôture.
- Le changement de `done_ratio` étant **journalisé nativement** par Redmine (comme
  le statut, cf. v1.15.0), il ne donne **pas** lieu à une note dédiée ; seules les
  modifications de **description** (texte/checklist) en justifient une.
- **Outillage** : `pm-task-description-update.py` (coche/décoche checklist,
  `--done-ratio auto`, `--set-from-file`, PUT + sync MD + log) ; garde-fou dans
  `pm-task-status-update.py` refusant `a_tester_verifier`/`ferme:resolu` avec des
  items de checklist non cochés (`--allow-unchecked` pour outrepasser).

Déclenché par RM1796 : checklist de la description cochée seulement à la fin (au
lieu du fil de l'eau), et besoin de suivre le % d'avancement.

---

## [1.15.0] - 2026-05-26

### Ajouté — Double traçabilité : note Redmine de synthèse pour l'humain

Complète la règle de journalisation de v1.14.0. Le `.log.md` est le journal de
travail de l'agent ; les **humains suivent les tickets dans Redmine** et ne lisent
pas les `.log.md`. Donc tout **échange consistant** (décision, arbitrage, jalon,
livraison) doit AUSSI être résumé dans une **note Redmine** lisible par un humain.

- **Discernement** explicitement requis : noter ce qui a une portée, pas chaque
  micro-aller-retour ; une session courte peut ne justifier qu'une seule note (voire
  aucune). Ne pas noyer le ticket sous le bruit.
- Réaffirme : **pas de note pour un simple changement de statut** (Redmine le
  journalise nativement) — une note ne se justifie que s'il y a qqch à dire en plus.
- Répartition : `.log.md` = détail technique au fil de l'eau ; note Redmine =
  synthèse à hauteur d'humain.

Déclenché par RM1793 : les échanges avaient été journalisés en `.log.md` mais rien
n'avait été poussé dans Redmine (invisible pour un humain consultant le ticket).

---

## [1.14.0] - 2026-05-26

### Ajouté — Journalisation des échanges humain↔agent + référencement de commit

Deux règles ajoutées à la section « Règles du journal (.log.md) » :

1. **Journalisation au fil de l'eau des échanges avec l'humain** : tout arbitrage,
   décision, re-cadrage du besoin ou retour de test concernant une tâche doit être
   résumé et appendé au `.log.md` au fur et à mesure (le *pourquoi* des décisions,
   pas seulement le code). Résumer, pas recopier verbatim.

2. **Référencement de commit** : toute entrée de journal qui produit/modifie du code
   doit citer le(s) commit(s) — forme canonique = SHA court ou URL de commit GitLab
   complète (cliquable). `git.branch`/`git.mr_url` = pointeur courant ; le `.log.md`
   garde l'historique par étape. Prérequis : workspace sous git (sinon le signaler).

Déclenché par RM1793 (outil de supervision LXC) : échanges itératifs de cadrage
(métrique RAM, dédoublonnage, vue ARC par hyperviseur) non tracés, et workspace
infra non initialisé en git → impossible de référencer la livraison par commit.

---

## [1.13.1] - 2026-05-20

### Précisé — 4e déclencheur de mise à jour de la description

Ajout d'un 4e cas obligeant à réécrire la description du ticket :
**modification substantielle de la demande en cours de travail** (re-cadrage
par le demandeur après rédaction initiale — rename de chemin, changement
d'identifiant, ajout/retrait d'item de périmètre). Une simple note de fix
n'est pas suffisante : la description doit refléter l'état final pour
servir de référence à la vérification.

Déclenché par RM1785 (restructuration matnat) où le demandeur a renommé
`erp_old/old` → `erp_old/dev` après création du ticket, et le fix avait
été tracé uniquement dans une note alors que la description listait encore
l'ancien chemin.

---

## [1.13.0] - 2026-05-18

### Ajouté — Règle de maintenance de la description du ticket Redmine

La description d'un ticket Redmine (corps principal, distinct des notes) est
un document **vivant** que l'agent doit maintenir à jour. Trois déclencheurs
obligatoires :

1. **Infos d'état dans la description** qui ont changé (statut en prose, URL
   d'env de test, version cible, décision provisoire) → réécrire la
   description, pas seulement contredire dans une note.
2. **Checklists Markdown `- [ ]` / `- [x]`** ou listes de tâches/sous-objectifs
   dont l'état évolue → cocher dans la description elle-même, pas uniquement
   en note. La description sert de tableau de bord, les notes d'historique.
3. **Demande explicite** du demandeur (« mets à jour la description avec X »,
   reformulation de périmètre, etc.).

Toute mise à jour de description doit être **accompagnée d'une note** résumant
ce qui a changé et pourquoi (Redmine ne diff pas les descriptions dans l'UI).

- **NORMS** : nouvelle sous-section « Mise à jour de la description du ticket
  Redmine (obligatoire) » sous « Lien Redmine ↔ MD », entre la table de
  mapping Redmine et « Flux de création de tâches ».
- **TODO scripts** : `pm-task-description-update.py` (lit description courante,
  ouvre `$EDITOR` ou applique un patch, PUT API + note auto + append `.log.md`).
  En attendant, mise à jour via appel direct API Redmine (`PUT /issues/<id>.json`
  avec champs `description` + `notes` dans le même appel).

---

## [1.12.0] - 2026-05-18

### Ajouté — Règle de prise en charge : `en_cours` ⇒ auto-assignation

Quand un agent commence à travailler sur une tâche, il doit, dans le même
mouvement, (1) passer le ticket en `en_cours` et (2) s'assigner le ticket
Redmine. Une tâche `en_cours` sans `assigned_to` cohérent devient un état
invalide.

- **NORMS** : nouvelle sous-section « Prise en charge d'une tâche : `en_cours`
  ⇒ auto-assignation (obligatoire) » sous « Synchronisation des statuts MD ↔
  Redmine ». Couvre explicitement le mode interactif (hors orchestrateur).
- **agents/worker-common.md** : la « Vérification initiale » distingue maintenant
  mode orchestré (signaler + s'arrêter si non aligné) et mode interactif
  (établir activement les deux conditions puis continuer).
- **TODO scripts** : coupler status + assignation dans `pm-task-status-update.py`
  (auto-assigner à l'agent courant quand cible = `en_cours`, user Redmine résolu
  via `pm.config.yml :: agents.<id>.redmine_id`, défaut karl=79). En attendant,
  l'agent enchaîne manuellement `pm-task-status-update.py` puis
  `redmine-post-note.py --assign-to`.

---

## [1.11.0] - 2026-05-17

### Ajouté — ROI assisté par IA (RM1717)

Chaque ticket porte désormais un coût (tokens + temps humain) et un gain
(immédiat + récurrent, € ou 1-5). Auto-incrémentation des tokens via hook
Claude Code Stop.

- **`pm.pricing.yml`** (nouveau) : tarification USD/MTok par modèle Claude
  (Opus 4.x, Sonnet 4.x, Haiku 4.x) — input/output/cache_read/cache_creation.
  Inclut aussi `human_hourly_rate_eur: 80` pour le ROI complet.
- **NORMS section « ROI assisté par IA »** : nouveaux champs frontmatter,
  cascade d'heuristiques pour identification du RM-id courant, formule de
  calcul ROI.
- **Frontmatter étendu** :
  - `estimate.{human_time_minutes, ai_time_minutes, cost_usd, estimated_model}`
  - `roi.{immediate_gain_eur, monthly_gain_eur}` (coexistent avec 1-5)
  - `tokens_breakdown.{input, output, cache_read, cache_creation}`
  - `cost_total_usd`, `human_time_total_minutes`, `ai_time_total_minutes`
  - `time_total_minutes` conservé pour compat (= human + ai)
- **`scripts/pm-task-tick.py`** (nouveau) : dual-mode
  - **hook Stop** : lit JSON sur stdin, identifie RM-id (cascade : sentinel
    global `~/.claude/current_task` → sentinel projet `.mmi-pm/CURRENT_TASK`
    → seule tâche `en_cours` dans le projet pointé par cwd `.mmi-pm`),
    extrait usage du dernier message assistant du transcript, calcule coût
    USD, met à jour le frontmatter, append au .log.md si > seuil (1000 tokens).
    Tickets non identifiés → log JSONL dans `~/.claude/logs/pm-task-tick-untracked.jsonl`.
  - **CLI manuel** : `pm-task-tick.py --rm-id X --tokens-input N --model M --human-minutes M ...`
    pour agents non-Claude-Code ou ajout post-hoc.
- **`~/.claude/settings.json`** : hook Stop configuré pour invoquer
  `pm-task-tick.py` à chaque réponse Claude (silencieux, jamais bloquant).
- **`templates/task.md`** et **`pm-task-add.py`** : schema 1.11.0, init des
  nouveaux champs à zéro/null.

### Tests pilotes

- CLI mode : `pm-task-tick --rm-id 1717 --tokens-input 5000 --tokens-output 2000
  --cache-read 30000 --cache-creation 1000 --model claude-opus-4-7` → tokens_total
  passe à 38000, cost_total_usd à $0.28875 (calcul exact vérifié contre la
  grille de prix).
- Hook mode : transcript factice avec 14800 tokens supplémentaires (1500/800/
  12000/500) → cost_total_usd passe à $0.398625 (+$0.10988, calcul exact ✓).

### Notes de migration

- Les tâches existantes (≤ v1.10.x) n'ont pas les nouveaux champs ; le hook
  les ajoute à la volée à la première écriture (`update_task_fm` lit le YAML
  existant, complète, réécrit).
- **Race conditions multi-Claude** : à valider en pratique. L'optimistic
  locking (`updated`) doit faire son job ; sinon prévoir un lock fichier.

### Hors scope (V2)

- Adaptation de `priority.py` pour calcul ROI €
- Dashboard `pm-roi.py` (drift prévu/effectif, cumulés)
- Sentinel `CURRENT_TASK` automatique (hook UserPromptSubmit qui parse les
  "RM1234" dans le prompt user pour set automatiquement)

---

## [1.10.0] - 2026-05-16

### Ajouté — Filtrage IA (RM1716)

Mutex de synchronisation entre l'instance Redmine (~1700 tickets historiques)
et le repo PM : seuls les tickets explicitement tagués `IA` sont fetchés en
MD et synchronisés. Évite l'engloutissement du repo par des journaux Redmine
non pertinents pour les agents IA.

- **Custom field global Redmine** `IA` (format `List`, valeurs : `IA`,
  `is_for_all: true`, tous trackers). À créer en UI Redmine (l'API REST
  ne supporte pas la création de CFs → HTTP 403). Id stocké dans
  `.env :: REDMINE_CF_IA_ID`.
- **Nouvelle section NORMS « Filtrage IA »** : règles d'intégrité,
  comportement des scripts, opt-in/opt-out, test d'un ticket.
- **`scripts/redmine_utils.py`** : module partagé — résolution credentials,
  `get_ia_cf_id()`, `issue_is_ia_tagged()`, `set_issue_ia_tag()`,
  `fetch_issue()`, `http_json()`.
- **`scripts/redmine-tag-ia.py`** : helper d'opt-in/opt-out (`tag` /
  `--untag`), déclenche `redmine-fetch-task` si nouveau tag.
- **`redmine-fetch-task.py`** : refuse de créer le MD si non tagué
  (option `--force` pour bypass).
- **`redmine-fetch-updates.py`** : skip la sync si non tagué, signale le
  drift quand le MD existe encore (option `--force`).
- **`pm-task-add.py`** : set automatiquement le CF `IA` au POST (les
  tickets créés depuis PM sont IA par construction).
- **`.env.example`** : ajout `REDMINE_CF_IA_ID=` documenté.
- Snapshot : `archive/NORMS_v1.9.0.md`.

### Notes de migration

Si `REDMINE_CF_IA_ID` n'est pas défini, le filtre est désactivé (mode
rétrocompat). Pour activer : créer le CF en UI Redmine, renseigner
l'id dans `.env`, puis tagger les tickets pertinents un par un via
`redmine-tag-ia.py`. **Ne pas** tagger en masse les 1700 tickets sans
réflexion (cela rendrait le filtre inutile et noierait le repo).

---

## [1.9.0] - 2026-05-16

### Ajouté — Champ `relates` et tooling `pm-task-link` (RM1709)

- **Schéma tâche** : nouveau champ `relates: list[int]` dans le frontmatter
  pour exprimer un lien **latéral non-bloquant** entre tickets (même famille
  de réflexion, sujet commun). Comble le gap entre `parent_task`/`sub_tasks`
  (hiérarchie), `depends_on`/`blocks` (dépendance bloquante), et `refs`
  (référence libre).
- **Section NORMS « Liens entre tâches »** : tableau récapitulatif des 4
  catégories de liens supportés (`parent`/`sub`, `depends_on`/`blocks`,
  `relates`, `refs`), leur sémantique, leur miroir côté cible, et le mapping
  vers les `relations` Redmine.
- **Script `scripts/pm-task-link.py`** : sous-commandes
  `add` / `list` / `rm` / `sync` qui maintiennent la cohérence Redmine ↔
  frontmatter PM ↔ `.log.md` pour les types `relates`, `depends_on`, `blocks`.
- **Skill `mmi-pm-task-link`** : wrapper langage naturel
  (« lie RM1234 et RM5678 », « liste les relations de RM1234 »).

### Modifié

- `templates/task.md` : `schema_version` 1.7.0 → 1.9.0 ; ajout de
  `relates: []` à la section Dépendances/Liens.
- `scripts/pm-task-add.py` : `schema_version` 1.7.1 → 1.9.0 ; ajout de
  `relates: []` dans le frontmatter généré.
- Snapshot archive : `archive/NORMS_v1.8.0.md`.

### Notes de migration

Les tâches existantes (créées en ≤1.8.x sans champ `relates`) restent valides
— l'absence du champ est interprétée comme `relates: []`. Le script
`pm-task-link sync` (ou `add`) ajoute le champ à la volée quand un nouveau
lien est créé.

---

## [1.8.0] - 2026-05-15

### Ajouté — Configuration centralisée des chemins (`pm.config.yml`)
- Nouveau fichier `pm.config.yml` à la racine du repo PM (commité, sans chemin
  absolu local — toutes les valeurs sensibles passent par `${VAR}` depuis `.env`)
- Nouvelle lib `scripts/pm_paths.py` (`PMConfig.load()`) qui résout tous les
  chemins du système via les patterns définis dans `pm.config.yml`
- Support d'un `pm.config.local.yml` (gitignored) pour surcharger localement
- Patterns standards documentés dans NORMS (`entities_dir`, `entity`,
  `entity_projects_dir`, `project`, `tasks_dir`, `task_file`, etc.)
- Lib expose : `cfg.path(key, **kwargs)`, `cfg.iter_entities()`,
  `cfg.iter_projects(entity=None)`, `cfg.find_task(rm_id)`,
  `cfg.find_project_by_redmine_id(slug_or_id)`

### Modifié — Symlink workspace → PM renommé en `.mmi-pm` (caché)
- Convention v1.5.1 : symlink `mmi-pm` (visible) → v1.8.0 : `.mmi-pm` (caché)
- Évite de polluer l'arborescence du code source côté workspace
- Les 2 symlinks existants (`/zfs/workspaces/redmine/mmi-pm`,
  `/zfs/workspaces/perso/mathematicians-db/mmi-pm`) ont été renommés
- La convention est désormais portée par `pm.config.yml :: paths.reverse_link`

### Modifié — Refacto des scripts pour passer par `pm_paths`
- `pm-dashboard.py`, `redmine-fetch-task.py`, `redmine-fetch-updates.py`,
  `pm-project-bootstrap.py` : suppression du hardcode `projects_root / "clients"`,
  remplacé par `cfg.path(...)` ou `cfg.iter_projects()`
- `priority.py`, `validate-task.py` : corrections de docstrings (exemples)
- `cron.example.sh`, `scripts/invoke.md` : références à `pm.config.yml`

### Modifié — NORMS reformulé en patterns logiques
- Tous les chemins littéraux `clients/{C}/projects/{P}/...` dans NORMS, agents,
  CLAUDE.md, README, templates → reformulés en `paths.X` ou `{pattern}` syntax
- L'arborescence "Repo projets" dans NORMS utilise désormais les noms de
  patterns (résolution par défaut indiquée pour référence humaine)
- Suppression du couplage doc ↔ structure filesystem actuelle

### Pourquoi
Permet de déplacer le repo PM, déplacer le repo projets, ou réorganiser la
structure interne (ex: flatten `projects/clients/` → `projects/`) sans toucher
au code des scripts ni à la doc des agents. Une seule ligne à modifier dans
`pm.config.yml` ou son override local.

---

## [1.7.2] - 2026-05-15

### Ajouté — Memberships par défaut sur nouveau projet Redmine
- Convention à inscrire pour tout nouveau projet Redmine de l'instance interne :
  - Groupe `Admin` (id 49) → rôle `Manager` (role_id 3)
  - Groupe `iProspective` (id 70) → rôle `Intervenant` (role_id 7)
- Payload API exemple pour `POST /projects/<id>/memberships.json`
- À automatiser dans le futur `pm project init` (TODO 003)

### Modifié
- NORMS schema bumped 1.7.1 → 1.7.2 (patch — additif)

---

## [1.7.1] - 2026-05-15

### Ajouté — Tâches de bootstrap projet + flow création projet PM↔Redmine
- Section NORMS "Création d'un projet PM ↔ Redmine" :
  - Mapping 1↔1 entre projet PM (slug) et projet Redmine (identifier)
  - Flow : lister API → vérifier existence → vérifier non-doublon côté PM
  - 3 cas : créer / réutiliser / bloquer (déjà utilisé ailleurs)
- Section NORMS "Tâches de bootstrap" :
  - 7 templates standards dans `templates/bootstrap-tasks/`
  - Convention `default_checked: true|false` par template
  - 3 premiers cochés par défaut (secrets, git-repos, environnements)
  - 4 autres optionnels (stack, deployment, testing, monitoring)
  - Flow d'instanciation via `scripts/pm-project-bootstrap.py` (à venir)
  - Création d'un ticket Redmine par template retenu (cohérent avec NORMS)
- Frontmatter `project/overview.md` enrichi :
  - `bootstrap.skip[]` : templates explicitement skippés
  - `bootstrap.done[]` : templates déjà appliqués (rempli auto)
- Templates créés dans `templates/bootstrap-tasks/` :
  - 001-secrets-vaultwarden, 002-git-repos, 003-environnements (cochés défaut)
  - 004-stack, 005-deployment, 006-testing, 007-monitoring (non cochés)

### Modifié
- NORMS schema bumped 1.7.0 → 1.7.1 (patch — additif rétrocompatible)
- Template `project-overview.md` : champ `bootstrap` + bump 1.6.0 → 1.7.1

---

## [1.7.0] - 2026-05-14

### Ajouté — Environnements et gestion des secrets
- Section NORMS "Environnements (aspect `environments.md`)" :
  - Énumération des noms standard : `local | dev | test | staging | preprod | prod | demo | qa | sandbox` + custom kebab-case
  - Schéma `environments[]` (status, url, admin_url, host, user, app_path, branch, fpm_pool, logs.{app,fpm}, secrets_source, notes)
  - Tableau `env_vars[]` (noms et descriptions des variables, sans les valeurs)
  - Cascade client → projet
- Section NORMS "Gestion des secrets — Vaultwarden" :
  - Convention `vaultwarden://<org>/<collection>/<item>` pour référencer un item
  - Architecture : organization iProspective + collections `<client>-agents` + user dédié `karl@iprospective.fr` (read-only)
  - Daemon `vault-agentd.py` : session BW en mémoire uniquement, socket Unix `/run/user/$UID/vault-agentd.sock`
  - Scripts associés : `unlock-vault.sh`, `resolve-secret.sh`, `lock-vault.sh`
  - Politique d'expiration configurable : `VAULT_IDLE_TIMEOUT` (défaut 8h) + `VAULT_LOCK_AT_HOUR` (défaut 23h)
  - Master password jamais stocké, tapé manuellement à chaque déverrouillage
  - Règles strictes : agent ne prompt jamais le mdp, secrets jamais loggués
- Schéma frontmatter tâche : nouveau champ `target_env`
- Template `aspects/common/environments.md` créé
- Template `aspects/common/hosting.md` resserré (centré sur provider/coûts/DNS, plus le mini-tableau env qui doublonnait)
- Template `task.md` bumped 1.5.2 → 1.7.0 + `target_env`
- `.env.example` étendu : `VAULT_URL`, `BW_CLIENTID`, `BW_CLIENTSECRET`, `VAULT_IDLE_TIMEOUT`, `VAULT_LOCK_AT_HOUR`

### Modifié
- NORMS schema bumped 1.6.0 → 1.7.0 (mineur — additif rétrocompatible)

---

## [1.6.0] - 2026-05-14

### Ajouté — Types d'entités + partage cross-client
- Section NORMS "Types d'entités (clients/)" : 3 types possibles
  - `client` : entité commerciale tierce (défaut)
  - `product` : écosystème produit (redmine, dolibarr, prestashop, symfony…)
  - `self` : entité interne / perso (iprospective, lemathou…)
- Règle d'arbitrage : suivre l'engagement de livraison / la responsabilité des données
- Section NORMS "Partage cross-client (used_by_clients / provided_by)" :
  - Champ `used_by_clients[]` côté projet fournisseur — liste des entités consommatrices
  - Champ `provided_by` côté projet consommateur — pointeur vers le fournisseur
  - Dossier `clients/<client>/projects_used/` (au même niveau que `projects/`)
    pour navigation humaine ; symlinks **générés** par `pm sync-views`, pas édités à la main
  - Cascade des aspects reste mono-client (héritage uniquement depuis `client:`)
  - Source de vérité = frontmatter ; les chemins canoniques pointent vers `clients/<owner>/`
- `client-overview.md` : champ `type` (`client` | `product` | `self`), défaut `client`
- `project-overview.md` : champs `used_by_clients` (liste) et `provided_by` (string|null)

### Ajouté — Symlink inverse `workspace` côté PM
- Convention bidirectionnelle : en plus du `mmi-pm` côté workspace → PM,
  ajout d'un symlink `workspace` côté PM → workspace, au même niveau que
  `project/`, `tasks/`, `memory/`
- Bénéfice : depuis le dossier PM d'un projet, accès direct au code source ;
  point de repère résiduel si l'un des deux dossiers est déplacé
- Symlinks en chemins **absolus** (workspace et PM ne sont pas systématiquement
  co-localisés)
- Scripts d'itération doivent ignorer ces symlinks (`find -P` ou `! -type l`)

### Modifié
- NORMS schema bumped 1.5.2 → 1.6.0 (mineur — additif rétrocompatible)
- Templates `client-overview.md` et `project-overview.md` bumped `schema_version: 1.6.0`
- Section NORMS "Workspace projet et symlink `mmi-pm`" renommée
  "Workspace projet — symlinks bidirectionnels `mmi-pm` ↔ `workspace`"

---

## [1.5.2] - 2026-05-13

### Ajouté — Workflow multi-tour
- 2 champs optionnels dans le frontmatter de tâche :
  - `redmine_last_journal_id: <int>` — id du dernier journal Redmine consulté
  - `redmine_last_checked_at: <str iso>` — timestamp du dernier check
- Section NORMS "Workflow multi-tour (reprise après notes du demandeur)" décrivant
  le protocole de reprise quand un ticket revient au worker
- Règle d'attribution Redmine étoffée :
  - `a_tester_verifier` → demandeur (auto via script)
  - `a_corriger` → worker précédent
  - `ferme` → attribution courante conservée

### Modifié
- Templates `task.md` et `RM9999_*.md` : `schema_version` 1.5.0 → 1.5.2 + nouveaux champs
- NORMS schema bumped 1.5.1 → 1.5.2 (patch — additif, pas d'archive)

---

## [1.5.1] - 2026-05-12

### Modifié
- Renommage du symlink de cohabitation : `.pm` → `mmi-pm`
  - Évite toute confusion avec l'extension de fichier Perl (`.pm`)
  - Symlink visible dans `ls` standard (au lieu de masqué par le `.`)
  - Préfixe `mmi-` cohérent avec d'autres conventions iprospective (skills `mmi-audit-*`, etc.)
- NORMS, worker-common, TODO/003 mis à jour
- Schema bumped 1.5.0 → 1.5.1 (patch — pas d'archive)

---

## [1.5.0] - 2026-05-12

### Ajouté
- **Convention `.pm` symlink** : chaque workspace projet (`/zfs/workspaces/{P}`) peut
  héberger un symlink `.pm` vers le dossier PM centralisé. Cohabite avec le code,
  conserve la centralisation. Documentée dans NORMS § Workspace projet et symlink `.pm`
- **Lien Redmine ↔ MD strict** (nouvelle section dans NORMS) :
  - `redmine_id` obligatoire pour les tâches (déjà required, désormais documenté)
  - Cohérence `RM{id}_*.md` ↔ `redmine_id` vérifiée par le validateur
  - `redmine.project_id` obligatoire dans `project/overview.md`
  - `redmine.subprojects[]` optionnel
- **Flux de création de tâches** documentés : Redmine→MD (humain) et CLI→Redmine+MD (à implémenter)
- `archive/NORMS_v1.4.0.md`

### Modifié
- Validator : nouvelle méthode `validate_redmine_coherence` (filename ↔ `redmine_id`)
- Template `task.md` : `schema_version` 1.0 → 1.5.0, annotation "OBLIGATOIRE" sur `redmine_id`
- Template `project-overview.md` : `redmine.project_id` marqué obligatoire, ajout `subprojects[]`
- Template `client-overview.md` : `schema_version` bumped
- `worker-common.md` : résolution de chemins via `$PROJECTS_PATH` (pas `.pm/../../`)
- Tableau "Nommage des fichiers" : références `project.md` → `project/overview.md`
- Schema bumped 1.4.0 → 1.5.0

---

## [1.4.0] - 2026-04-27

### Ajouté — Cahier des charges dynamique
- `client/` et `project/` deviennent des **dossiers** contenant des aspects
- `overview.md` est obligatoire (porte le frontmatter et l'index des aspects)
- Tout autre fichier dans le dossier est un aspect optionnel
- Cascade aspect par aspect : `client/{aspect}.md` + `project/{aspect}.md` coexistent
  (le projet précise/surcharge le client)
- 40 templates d'aspects organisés par domaine dans `templates/aspects/` :
  - `common/` (10) : hosting, stack, data-model, workflows, testing, deployment,
    monitoring, security, conventions, roadmap
  - `website/` (6) : audience, seo, pages, cms, design-system, i18n
  - `ecommerce/` (6) : catalogue, payment, fulfillment, customer-journey, promotions, taxes
  - `api/` (5) : endpoints, rate-limits, auth, webhooks, consumers
  - `saas/` (4) : tenants, subscriptions, onboarding, support
  - `mobile/` (4) : platforms, distribution, parity, permissions
  - `data/` (4) : pipelines, warehouse, dashboards, compliance
  - `legal/` (3) : contracts, sla, confidentiality
- Templates `client-overview.md` et `project-overview.md` (séparés, gèrent le frontmatter)

### Modifié
- Renommage `templates/client.md` → `templates/client-overview.md`
- Renommage `templates/project.md` → `templates/project-overview.md`
- `worker-common.md` : charge tous les fichiers du dossier `client/` et `project/`
- `summarizer.md` : peut créer de nouveaux aspects depuis les `templates/aspects/`
- Schema bumped 1.3.0 → 1.4.0
- `archive/NORMS_v1.3.0.md` créé

---

## [1.3.0] - 2026-04-27

### Ajouté
- **Hiérarchie client → projet → tâche** : nouvelle structure
  `clients/{C}/projects/{P}/tasks/RM*.md`
- **Cascade et héritage** : règles de propagation des paramètres entre niveaux
  (héritage par défaut, override possible)
- **Fichiers auto-générés** au niveau client et projet :
  `Changelog.md`, `Pistes.md`, `Remarques.md`
- **Section "Structure / Fonctionnement"** dans `client.md` et `project.md`
  (rédigée par l'agent summarizer)
- **Section "Ordonnancement par ROI"** : formule de scoring documentée
- Template `client.md` (nouveau)
- `archive/NORMS_v1.2.1.md`

### Modifié
- Template `project.md` : ajout `client`, `defaults`, `stack` (incluant section tests),
  section `## Structure / Fonctionnement`
- Schema bumped 1.2.1 → 1.3.0

---

## [1.2.1] - 2026-04-27

### Modifié
- Configuration globale : URLs et credentials remplacés par des références `${VAR}`
  — les valeurs réelles vont dans `.env` (gitignored)
- `archive/NORMS_v1.2.0.md` ajouté

---

## [1.2.0] - 2026-04-27

### Ajouté
- Types de tâches `database` et `design` dans l'énumération `type`
- `agents/worker-db.md` : modélisation BDD, migrations avec UP/DOWN obligatoire, sécurité des données
- `agents/worker-design.md` : wireframes, prototypes HTML, specs composants, cycle itératif avec feedback
- `agents/worker-infra.md` : CI/CD, configuration serveur, déploiement, gestion des secrets
- Table de routage type → agent mise à jour dans NORMS.md et orchestrateur.md
- `archive/NORMS_v1.1.1.md` — snapshot de la version précédente

---

## [1.1.1] - 2026-04-27

### Modifié
- Règle de versionning : les versions **mineures** sont désormais archivées dans `archive/` (comme les majeures). Seuls les patches restent sans archive.
- Description du dossier `archive/` mise à jour en conséquence

### Ajouté
- `archive/NORMS_v1.0.md` — snapshot de la version initiale
- `archive/NORMS_v1.1.md` — snapshot de la v1.1

---

## [1.1.0] - 2026-04-27

### Ajouté
- Section **Collaboration multi-agents** complète :
  - Principe fondamental : Redmine comme mutex, MD comme contexte de travail
  - Définition des rôles : orchestrateur, workers spécialisés, reviewer
  - Table des règles d'écriture par rôle et type de fichier
  - Protocole de prise en charge d'une tâche (10 étapes)
  - Gestion des sous-tâches multi-niveaux avec propagation bottom-up du `completion_pct`
  - Protocole optimistic locking sur le champ `updated`
  - Règles append-only pour les `.log.md`
- Section **Architecture de déploiement** complète :
  - V1 : machine unique (actuelle)
  - V1.5 : NFS sur ZFS pour ajout de serveurs sans refonte
  - V2 : Git/branches GitLab pour distribution robuste
  - Tableau de sélection selon contexte

---

## [1.0.0] - 2026-04-26

### Initial
- Structure de dossiers et conventions de nommage
- Schéma frontmatter complet pour les tâches
- Machine d'états avec 7 statuts et transitions validées
- Séparation tâche (stable) / journal append-only (.log.md)
- Champs ROI : `immediate_benefit` + `monthly_benefit` (/5)
- Estimation IA : `difficulty`, `time_minutes`, `tokens`, `confidence`
- Suivi tokens et temps cumulés (`tokens_total`, `time_total_minutes`)
- `status_history` avec modèle IA, tokens et durée par étape
- Support sous-tâches : `parent_task` + `sub_tasks[]`
- Champ `pistes[]` structuré pour idées futures (label, type, effort)
- Références externes `refs[]` (Redmine partenaire, docs, URLs)
- Intégration GitLab : `git.repo`, `git.branch`, `git.mr_url`
- Environnement de test : `test_url`
- Actions de déploiement : `deploy_actions[]`
- Champs bug : `reproducibility` + `reproduce_steps` + `conditions`
- Templates task.md et project.md
- Configuration globale GitLab dans NORMS.md
