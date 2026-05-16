# Changelog des normes

Toutes les évolutions notables sont documentées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/)

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
