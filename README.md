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

Mise à jour d'une instance : `mmi-pm core-update` (sudo demandé par la commande ; pull + re-verrou 3 couches
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

### Noter ses heures (feuille de temps)

```bash
mmi-pm timesheet --month 2026-08          # rapport .md + proposition .yml amendable
$EDITOR var/timesheet/2026-08.yml         # on relit, on corrige
mmi-pm timesheet --month 2026-08 --apply  # crée les saisies dans Redmine (idempotent)
```

Une journée à la fois : `mmi-pm timesheet --day 2026-08-26 [--start 09:30 --end 18:30
--client matnat]`, puis `--apply`. Réglages dans `<core>/var/users/<user>/timesheet.yml`.

Reconstitue le temps de travail **humain** à partir des traces des agents
(transcripts, journaux de tickets, bases opencode), le répartit par
client / projet / ticket, refacture le transversal aux clients du jour et
retranche ce qui est déjà saisi. Sans appel à un modèle. Réglages :
`timesheet.example.yml` → `timesheet.yml`.

### Préparer les factures du mois

```bash
mmi-pm invoice --month 2026-08            # rapport .md + proposition .yml — rien n'est créé
```

Regroupe le temps saisi dans Redmine par client et par activité, au tarif de la dernière
facture, avec la note publique habituelle et les mises en production du mois. L'ERP est
le provider `erp` du registre ; réglages : `invoice.example.yml` → `<core>/var/users/<user>/invoice.yml`.

## Le carnet de réflexion : de la question au ticket

Chaque ticket a trois fichiers. Le `.md` est le **contrat**, le `.log.md` le **journal
d'événements**, et le `.think.md` le **pourquoi** — c'est le carnet de réflexion. Il porte
quatre rubriques, et c'est la chaîne qui les relie qui compte.

| | Rubrique | Ce qu'on y range |
|---|---|---|
| **N** | Notes | une information utile plus tard, **verbatim, jamais reformulé** — jamais une demande immédiate, un accord, un accusé |
| **Q** | Questions | ce qui **n'est pas tranché** : ce que ça bloque, l'urgence |
| **D** | Décisions | ce que le demandeur demande, pose ou **tranche** — réponse à une question ou non, **ticketé ou non** |
| **C** | Conseils | l'avis de l'agent, 🟡 jusqu'à l'arbitrage |
| **F** | Fonctionnalités | une **capacité atomique** du système |

### La chaîne

```
Q (pas tranché)  →  D (l'arbitrage, tracé quoi qu'il arrive)  →  parfois F  →  ticket(s)
```

Deux malentendus fréquents, tranchés ici :

- **Une décision ne donne PAS toujours une fonctionnalité.** Elle n'en donne une que si elle
  implique une **capacité nouvelle**. Un arbitrage de méthode, de politique ou de priorité se
  trace et s'arrête là — c'est une décision complète, elle n'a rien à implémenter.
- **Une fonctionnalité n'est PAS un ticket.** Une fonctionnalité est *ce que le système sait
  faire* : elle existe pour elle-même, se dit en langage d'usage, et **cite 0, 1 ou plusieurs
  tickets**. Elle peut donner lieu à un ticket, **en compléter** un, ou rester à faire. Le ticket
  est une trace de travail, pas la définition.

Corollaire : **les décisions non ticketées sont tracées**, et elles ne meurent pas avec le
ticket — `pm-think-merge` fait remonter les carnets vers les registres du projet
(`docs/cdc-decisions.md`, `cdc-questions.md`, `cdc-notes.md`, `cdc-features.md`), où les ids sont
préfixés `RM<id>-`. Le cockpit les expose dans son panneau **CDC**.

### Les gestes

```bash
mmi-pm task-think <id> --note "verbatim"            # consigner sans reformuler
mmi-pm task-think <id> --question "…" --bloque X    # ce qui n'est pas tranché
mmi-pm task-think <id> --decide "…"                 # l'arbitrage
mmi-pm task-think <id> --feature "…"                # une capacité
mmi-pm task-think <id> --show                       # ce que porte le ticket
```

Deux règles sont **tenues par l'outil**, pas par la discipline :

- **Trancher une question appelle sa décision.** `--set Qnnn --state valide` est refusé si rien
  ne tranche la question. Trois sorties : `--decide-with "…"` (pose la décision et la relie, en un
  appel), `--dest Dnnn` (relier une décision existante), ou `--state invalide` si ce n'était pas
  une question — **écarter n'est pas trancher**. `--orphans` liste les questions tranchées que rien
  ne relie.
- **Une entrée mal classée se requalifie, elle ne se détruit pas.**
  `--requalify Qnnn --as note` change de rubrique en gardant date, auteur, état et texte ; la
  colonne `Origine` garde la piste (`ex-Q001`). C'est ce qui débloque un ticket qu'une capture
  accidentelle empêchait de fermer — **une question ouverte bloque la clôture**.

> La norme qui fait foi est `norms/src/modules/cdc.md` (§ codes de lettres) ; le détail des gestes
> est dans `mmi-pm task-think --help`. Cette section les résume, elle ne les remplace pas.

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
    mmi-pm                             # coquille de transition (RM3033) → scripts/mmi-pm.py, LE point d'entrée
  deploy/
    karl-agent/                        # cockpit web : karl-agent.py (service), cockpit/ (UI 3.x :
                                       # index.html + src/{boot.js,core,modules/<domaine>,styles},
                                       # cockpit.css compilé, help/ aide intégrée, tooling/ build
                                       # SCSS, test_cockpit*.js — voir cockpit/README.md),
                                       # units systemd (service USER dans le conteneur dev),
                                       # karl-askpass.sh (passphrase SSH par descripteur, RM2748)
  skills/                              # skills mmi-pm-* distribués (pm-skills-sync)
  scripts/                             # ~50 outils pm-*/redmine-* — quelques familles :
    pm_paths.py                        # lib résolution de chemins (PMConfig)
    pm-task-*.py                       # add, status-update, comment, link, protocol, blockers…
    pm-env-*.py                        # init, migrate, session (envs par ticket), deploy
    pm-mr.py · pm-branch-start.py      # branche par ticket, MR fiable (create/merge/get)
    pm-norms-assemble.py · -doctor.py  # gouvernance NORMS (build + invariants)
    pm-workspace-bridge.py             # pont d'onboarding des workspaces (AGENTS.md + CLAUDE.md)
    karl-mail-*.py                     # boîte de karl : send, fetch (relève), route
                                       # (client/projet), draft (ticket à la validation)
    pm-client-contact.py               # contacts d'un client (nom, prénom, email, tél)
    unlock-vault.sh · lock-vault.sh    # coffre de secrets : ouvrir (invite, ou --stdin pour
                                       # un appelant non interactif — le cockpit), fermer
    vault-agentd.py · resolve-secret.sh # daemon en mémoire + résolution `secret://…`
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

## Licence

Ce code est publié sous **GNU General Public License v3.0 or later** (`GPL-3.0-or-later`,
décision iProspective du 2026-09-07, RM3029) — texte intégral dans [LICENSE](LICENSE), copyright
iProspective. Concrètement : libre d'usage, d'étude, de modification et de redistribution, à
condition de conserver la licence et de publier les sources de toute version modifiée que l'on
distribue. Un **module** ou une extension distribuée avec le cœur (ou qui en dérive) doit être sous
une licence compatible GPL ; l'usage interne, sans redistribution, n'impose rien. Les dépendances
vendorées du cockpit (xterm.js, MIT) sont compatibles — voir
[deploy/karl-agent/cockpit/vendor/PROVENANCE.md](deploy/karl-agent/cockpit/vendor/PROVENANCE.md).
Toute contribution au repo est faite sous cette même licence (norme « Développement du PM »).

Les **données** de projets (clients, tickets, journaux) vivent dans un dépôt séparé et privé :
elles ne sont pas couvertes par cette licence.

## Références

- Normes courantes : [norms/NORMS.md](norms/NORMS.md) (version : `norms/VERSION`)
- Profil dev CLI-seul (sans cockpit) : [docs/guides/travailler-le-pm-en-cli-sans-cockpit.md](docs/guides/travailler-le-pm-en-cli-sans-cockpit.md)
- Config des chemins : [pm.config.yml](pm.config.yml)
- Lib : [scripts/pm_paths.py](scripts/pm_paths.py)
- Redmine : défini globalement dans `.env`, surchargeable dans `project/overview.md`
- GitLab : https://gitlab.iprospective.fr
