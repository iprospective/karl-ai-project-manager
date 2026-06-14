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
| `001-secrets-vaultwarden` | Setup items Vaultwarden + remplir `secrets_source` des envs | ✅ |
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

