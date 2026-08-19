# Système de gestion de tâches — iprospective

Système de gestion de projets et tâches conçu pour la collaboration entre humains et agents IA.
Les tâches sont des fichiers Markdown structurés, Redmine est le tracker opérationnel, GitLab assure
le versioning. Un **cockpit web** (`deploy/karl-agent/`) supervise les sessions d'agents, expose la
surface CLI (command-catalog) et porte la **console de test/revue** des tickets livrés.

## Installation

**Installeur d'instance** (RM2062) — chemin recommandé, il pose le clone root-owned
(privsep RM2032), le `.env`, l'alias `mmi-pm` sur le PATH et les skills :

```bash
./install-mmi-pm            # depuis un clone frais ; voir --help
```

Mise à jour d'une instance : `sudo mmi-pm core update` (pull + re-verrou 3 couches
via `core-lock` ; une seule passphrase SSH — multiplexing RM2069 + agent éphémère RM2239).

Étapes manuelles équivalentes (dev / instance jetable) :

```bash
git clone git@gitlab.iprospective.fr:iprospective/ai-artificial-intelligence/ai-project-management.git
cd ai-project-management
cp .env.example .env        # GitLab token, Redmine API key, PROJECTS_PATH…
python3 scripts/pm-skills-sync.py   # skills PM → ~/.claude/skills/
# optionnel : pm.config.local.yml (surcharge gitignorée de pm.config.yml)
```

## Démarrage rapide

Tous les chemins ci-dessous sont **logiques** (patterns de `pm.config.yml`).
Leur résolution filesystem se fait via `scripts/pm_paths.py` (`PMConfig.path(...)`)
ou par défaut : `{projects_root}/clients/<entity>/projects/<project>/...`.

### Créer une entité (client / produit / self)
1. Copier `templates/client.md` dans `cfg.path("entity_client_dir", entity="<slug>")/overview.md`
2. Remplir les champs (slug, nom, type, contacts, defaults hérités)

### Créer un projet sous une entité existante
1. Copier `templates/project.md` dans `cfg.path("project_dir", entity="<C>", project="<P>")/overview.md`
2. Remplir les champs (slug, client, stack, intégrations, `redmine.project_id`)
3. Créer le dossier des tâches `cfg.path("tasks_dir", entity="<C>", project="<P>")`

### Créer une tâche
```bash
# Fetch automatique depuis Redmine (recommandé)
python3 scripts/redmine-fetch-task.py --issue 1234

# Le chemin de destination est résolu via pm.config.yml :: paths.task_file
```

### Nommage des fichiers
| Élément | Pattern (clé) | Format |
|---|---|---|
| Tâche | `paths.task_file` | `RM{id}_{titre-en-kebab-case}.md` |
| Journal | `paths.task_log_file` | `RM{id}_{titre-en-kebab-case}.log.md` |

## Structure du repo

```
project-management/                    # = pm.config.yml :: roots.pm_dir
  README.md                            # ce fichier
  Changelog.md                         # historique système
  PISTES.md                            # pistes d'évolution
  pm.config.yml                        # config des chemins (commitée)
  pm.config.local.yml                  # surcharge locale (gitignored, optionnel)
  mail-routing.yml                     # routage email → client/projet (appris, RM2669)
  .env                                 # credentials + PROJECTS_PATH (gitignored)
  .gitignore
  norms/
    NORMS.md                           # référence normative GÉNÉRÉE (ne pas éditer)
    VERSION                            # version courante des normes
    CHANGELOG.md                       # historique des évolutions du schéma
    src/
      NORMS-KERNEL.md                  # noyau runtime : déclencheurs + tripwires
      modules/*.md                     # modules chargés à la demande (sources)
      dedup-ledger.yml                 # registre des écarts au verbatim (non-perte)
    archive/                           # snapshots des versions
  agents/
    worker-common.md                   # règles communes des workers
    worker-{role}.md                   # rôles spécifiques (dev, analyst, db, infra, design)
    orchestrateur.md
    reviewer.md
    summarizer.md
  bin/
    mmi-pm                             # CLI d'instance (core update, index, doctor…)
  deploy/
    karl-agent/                        # cockpit web : karl-agent.py (service), cockpit/ (UI),
                                       # units systemd (service USER dans le conteneur dev)
  skills/                              # skills mmi-pm-* distribués (pm-skills-sync)
  scripts/                             # ~50 outils pm-*/redmine-* — quelques familles :
    pm_paths.py                        # lib résolution de chemins (PMConfig)
    pm-task-*.py                       # add, status-update, comment, link, protocol, blockers…
    pm-env-*.py                        # init, migrate, session (envs par ticket), deploy
    pm-mr.py · pm-branch-start.py      # branche par ticket, MR fiable (create/merge/get)
    pm-norms-assemble.py · -doctor.py  # gouvernance NORMS (build + invariants)
    karl-mail-*.py                     # boîte de karl : send, fetch (relève), route
                                       # (client/projet), draft (ticket à la validation)
    pm-client-contact.py               # contacts d'un client (nom, prénom, email, tél)
    redmine-fetch-task.py · redmine-post-note.py · pm-project-bootstrap.py …
  templates/
    task.md                            # template tâche
    project.md                         # template projet
    client.md                          # template client
    aspects/                           # templates d'aspects (hosting, stack, environments…)
    bootstrap-tasks/                   # templates de tâches de bootstrap projet

# Repo séparé (chemin = $PROJECTS_PATH, défini dans .env)
$PROJECTS_PATH/                        # = pm.config.yml :: roots.projects_root
  clients/                             # = paths.entities_dir
    <entity>/                          # client | product | self
      client/                          # cahier des charges (overview + aspects)
      memory/                          # mémoire structurée
      projects/
        <project>/
          project/                     # cahier des charges projet
          memory/
          tasks/
            RM{id}_*.md                # = paths.task_file
            RM{id}_*.log.md            # = paths.task_log_file
          workspace                    # symlink → workspace de code
```

Côté workspace de code (ex: `/zfs/workspaces/<P>/`) : un `.mmi-pm` caché relie le
workspace à son volet PM — **symlink** vers `projects/…` (modèle historique) ou
**dossier co-localisé versionné** dans le workspace (modèle RM1949/RM2228, fichiers
partagés avec l'arbo centrale). `pm-workspace-coloc` gère la conversion.

## Pour les développeurs

Pour développer le système PM lui-même (architecture, flux, boucle de dev,
« comment contribuer ») : **[DEVELOPMENT.md](DEVELOPMENT.md)** — point d'entrée
qui relie README, normes, `knowledge/` et `docs/`.

## Pour les agents IA

**Ordre de lecture au démarrage :** voir `CLAUDE.md` à la racine et `agents/worker-common.md`.

**Règle fondamentale :** Redmine est le mutex. L'assignation d'un ticket Redmine à un agent lui confère la propriété exclusive du fichier MD correspondant.

## Références

- Normes courantes : [norms/NORMS.md](norms/NORMS.md) (version : `norms/VERSION`)
- Profil dev CLI-seul (sans cockpit) : [docs/guides/travailler-le-pm-en-cli-sans-cockpit.md](docs/guides/travailler-le-pm-en-cli-sans-cockpit.md)
- Config des chemins : [pm.config.yml](pm.config.yml)
- Lib : [scripts/pm_paths.py](scripts/pm_paths.py)
- Redmine : défini globalement dans `.env`, surchargeable dans `project/overview.md`
- GitLab : https://gitlab.iprospective.fr
