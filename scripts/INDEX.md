# INDEX des scripts PM — généré, ne pas éditer

> `pm-norms-assemble.py index`. Vérifié par `pm-norms-doctor` (fraîcheur).
> Détail d'un outil : `<script> --help` (court) · `--help-full` (docstring entière).
> Tout `pm-<verbe>.py` s'invoque aussi `mmi-pm <verbe>` (verbe en UN token tiret).
> Condensé des outils du quotidien, préchargé par tous : `norms/CHEATSHEET.md`.

## Exécutables

### Tâches & tickets

- `pm-cf-git-backfill` — rétro-remplit les CF « GIT Branche » / « GIT PR »
- `pm-cf-mirror-backfill` — reprise de l'existant des miroirs « frontmatter ↔ CF »
- `pm-task-add` — Crée une nouvelle tâche (POST Redmine + MD + log + valide).
- `pm-task-blockers` — pourquoi un ticket ne peut pas changer de statut / être fermé.
- `pm-task-brief` — le « pack contexte » d'un ticket en ≤ 30 lignes
- `pm-task-cd` — imprime le chemin de travail d'un ticket (frontmatter `git.worktree`).
- `pm-task-comment` — Poste une note Redmine ET append au log local.
- `pm-task-deliver` — livraison d'un ticket en UN appel
- `pm-task-deploy` — actions à effectuer au déploiement : CF Redmine + frontmatter
- `pm-task-description-update` — Met à jour la DESCRIPTION d'un ticket Redmine + sync MD.
- `pm-task-doc` — adosser une doc partagée (aspect) à un ticket
- `pm-task-estimate` — RÉVISER l'estimation d'un ticket (frontmatter + Redmine). RM3155.
- `pm-task-implementation` — esquisse d'implémentation d'un ticket : CF Redmine + frontmatter
- `pm-task-import` — ADOPTE un ticket Redmine existant en fiche PM locale.
- `pm-task-link` — Gestion des liens entre tickets PM (Redmine + frontmatter + log).
- `pm-task-list` — Liste les tâches d'un projet PM (depuis MD).
- `pm-task-log` — lecture CIBLÉE du journal d'un ticket
- `pm-task-metrics-push` — Pousse l'ESTIMATION d'une tâche vers Redmine.
- `pm-task-move` — DÉPLACE une tâche d'un projet PM vers un autre (fichiers + Redmine).
- `pm-task-partner` — rattache un ticket PM à un ticket d'un gestionnaire PARTENAIRE.
- `pm-task-protocol` — Protocole de test d'un ticket : CF Redmine + frontmatter
- `pm-task-questions` — les questions d'un ticket, dans sa description
- `pm-task-report` — Report des tokens/temps consommés (frontmatter + .log.md PM) → Redmine.
- `pm-task-search` — recherche d'ANTÉRIORITÉ : ce sujet a-t-il déjà un ticket ?
- `pm-task-show` — Affiche le détail d'une tâche (MD + tail log + Redmine récent).
- `pm-task-status-update` — Change le statut d'une tâche (Redmine + MD frontmatter + log).
- `pm-task-sync` — Synchronise une tâche MD locale avec son état actuel Redmine.
- `pm-task-tag` — étiquettes d'un ticket
- `pm-task-take` — prise d'un ticket en UN appel
- `pm-task-think` — consigner dans le fichier de réflexion d'un ticket (`RM<id>_<slug>.thin…
- `pm-task-tick` — Incrémente tokens/coût/temps sur le frontmatter d'une tâche PM.
- `pm-think-classify` — classe les tours d'une conversation par un LLM LÉGER, au lieu d'une heu…
- `pm-think-harvest` — moisson automatique du transcript vers le `.think.md` du ticket courant…
- `pm-think-merge` — fusionne les `.think.md` des tickets vers les fichiers du projet. RM301…
- `pm-tick-backfill` — reconstitue les ticks de conso manqués depuis les transcripts

### Projets, clients & contacts

- `pm-client-contact` — contacts d'un client : nom, prénom, email, téléphone
- `pm-client-new` — Crée un nouveau client/produit/self dans l'arbo PM.
- `pm-client-notify` — notification client à la MEP
- `pm-contact` — l'annuaire de contacts, indépendant des clients
- `pm-index-add` — index des projets PM : les liens de co-localisation (RM3033). Voir pm_i…
- `pm-index-list` — index des projets PM : les liens de co-localisation (RM3033). Voir pm_i…
- `pm-index-rebuild` — index des projets PM : les liens de co-localisation (RM3033). Voir pm_i…
- `pm-index-remove` — index des projets PM : les liens de co-localisation (RM3033). Voir pm_i…
- `pm-project-bootstrap` — Bootstrap a PM project by instantiating bootstrap-tasks templates.
- `pm-project-config` — édite la conf structurée d'un projet ou d'un client
- `pm-project-new` — Pipeline complet : Redmine + struct PM + symlinks + bootstrap.

### Git, MR & MEP

- `pm-branch-start` — Crée la branche de travail d'un ticket (NORMS git-mep ; RM1923 #1 / RM1…
- `pm-git-recable` — Recâble en masse les remotes git locaux après un déplacement de groupe…
- `pm-gitlab-push-check` — watchdog : karl peut-il pousser sur GitLab ?
- `pm-gitlab-rename` — Renomme/déplace un repo GitLab + recâble les remotes locaux
- `pm-mr` — outillage Merge/Pull Request fiable
- `pm-post-commit` — hook git post-commit (repos PM-trackés).
- `pm-pre-commit` — garde-fou « bon worktree / bonne branche »
- `pm-promote` — promotion par lot intégration → branche protégée
- `pm-protect` — applique la politique NORMS de branches protégées
- `pm-repo-new` — crée un dépôt sur la forge, conforme aux NORMS, sans étape manuelle.
- `pm-reporting-migrate` — externalise l'historique reporting vers le ledger annexe
- `pm-workspace-bridge` — pose et tient à jour le pont d'onboarding des workspaces
- `pm-workspace-coloc` — Co-localise les données PM d'un client dans ses workspaces
- `pm-worktree` — liste / supprime les git worktrees enregistrés par session

### Environnements

- `pm-env-audit` — audit hebdomadaire de TOUS les environnements
- `pm-env-deploy` — déployer la branche d'un ticket dans un env PARTAGÉ du projet
- `pm-env-expose` — expose un env de test via un hostname normalisé
- `pm-env-gc` — GC des worktrees & branches locales des tickets fermés
- `pm-env-init` — instancie le LAYOUT GIT d'un workspace projet
- `pm-env-migrate` — migre un workspace PRÉ-NORME vers le layout RM1993
- `pm-env-session` — env de SESSION par ticket : worktree + runtime
- `pm-env-status` — santé du poste PM, en une commande
- `pm-env-vhost` — façade CLI des verbes vhost du helper privilégié

### Sessions, cockpit & agents

- `karl-agent` — superviseur de sessions d'agents karl-pm (backend, RM1771).
- `karl-mail-draft` — d'un email de la file à un ticket, à la validation
- `karl-mail-fetch` — relève IMAP de la boîte de karl → file de triage
- `karl-mail-route` — routage des emails de la file : qui est le client, quel projet
- `karl-mail-send` — Envoie un email depuis karl@iprospective.fr via SMTP iProspective.
- `karl-move-session` — déplace une session Claude Code d'un projet à un autre.
- `karl-sms-private-send` — Notification SMS privée via l'API SMS Free Mobile.
- `karl-telegram-bot` — Bot Telegram « standardiste » de karl-pm (épic A, RM1724).
- `karl-whisper-sidecar` — sidecar STT local pour le cockpit
- `pm-session-relocate` — Déplace les sessions Claude quand un workspace change de chemin
- `pm-session-status` — Suivi par session des tickets/tâches ouverts et de leur avancement.
- `pm-sessions-archive` — archive les sessions Claude dans leur dépôt git
- `pm-turn-start` — hook UserPromptSubmit : pose le timestamp de début de tour.
- `pm-turn-wait` — hooks PreToolUse / PostToolUse (matcher AskUserQuestion|ExitPlanMode).

### Redmine

- `redmine-config-check` — Diffe la config Redmine live contre la référence locale.
- `redmine-fetch-task` — Fetcher un ticket Redmine et générer le fichier MD correspondant.
- `redmine-fetch-updates` — Récupérer les nouveautés Redmine sur un ticket depuis le dernier check.
- `redmine-post-note` — Poster une note sur un ticket Redmine (et optionnellement changer son s…
- `redmine-purge-commit-notes` — purge des notes de journal « commit d'outillage ».
- `redmine-tag-ia` — Opt-in / opt-out d'un ticket Redmine pour la sync PM.
- `redmine-template-sync` — Copie un contenu local vers remote via `ssh host 'cat > remote'`.
- `redmine-test` — Test de connexion Redmine — vérifie URL, API key, projets accessibles.

### NORMS, CDC & documentation

- `pm-cdc-features` — le registre des FONCTIONNALITÉS d'un projet
- `pm-cdc` — outillage du CDC complet : ouvrir, générer, vérifier
- `pm-decisions` — extrait les questions/réponses d'une session et les consigne
- `pm-dict-from-pm` — les tables GÉNÉRÉES du dictionnaire des données du projet PM
- `pm-docs-migrate` — sort les aspects-docs LIBRES de .mmi-pm/project/ vers .mmi-pm/docs/
- `pm-glossaire` — le vocabulaire métier d'un projet
- `pm-norms-assemble` — génère norms/NORMS.md par concaténation des sources norms/src/.
- `pm-norms-changes` — sais-je si ma connaissance de NORMS est à jour ?
- `pm-norms-doctor` — vérifie les invariants de la structure NORMS (cf. MAINTAINING.md §11).
- `pm-norms-recall` — remet le KERNEL NORMS dans le contexte quand celui-ci vient d'être perdu
- `pm-norms-runtime` — produit et contrôle le runtime NORMS, par l'API d'un fournisseur du reg…
- `pm-skills-sync` — expose les skills PM (skills/) à Claude Code via des symlinks.
- `pm-wiki-sync` — Synchronise les docs de design d'un projet PM ⇄ son Wiki Redmine.

### Mesure, coût & reporting

- `pm-bench-overhead` — Benchmark de la surconsommation de la couche PM
- `pm-conso-report` — Compte-rendu de consommation tokens / coût / temps
- `pm-context-budget` — Mesure le contexte « toujours chargé » d'une session PM par rôle
- `pm-dashboard` — PM Dashboard — vue d'ensemble du système de gestion de tâches.
- `pm-file-heatmap` — carte de chaleur d'un fichier : qui l'a touché, et où.
- `pm-log-tail` — lit le journal structuré (RM3010) : `mmi-pm log-tail [--category auth,a…
- `pm-pricing-backfill` — recalcule `cost_total_usd` des tickets dont le coût a été
- `pm-pricing-check` — Vérifie pm.pricing.yml contre la doc officielle Anthropic.
- `pm-stats` — Résumé synthétique du système PM (depuis les MD locaux).
- `pm-timesheet` — reconstitue et note le temps de travail HUMAIN

### Secrets & coffres

- `pm-provider-secret` — pose, remplace ou efface le SECRET d'une instance de provider
- `pm-providers` — inspecte le registre de serveurs et la résolution d'instance

### Ordonnancement & notifications

- `pm-lock-gc` — GC des fichiers .lock (T7/RM2551) : filet post-crash + observabilité.
- `pm-notify-mail` — le canal mail du fil de notifications
- `pm-notify` — le fil de notifications de l'instance : lire, marquer, émettre
- `pm-scheduler` — ordonnanceur unique des travaux périodiques PM

### Installation, migration & maintenance

- `mmi-pm` — point d'entrée UNIQUE du système PM
- `pm-claude-hooks-sync` — installe le bloc de hooks PM dans le settings.json Claude Code.
- `pm-cockpit-remap` — où reporter une branche partie de l'ancien index.html.
- `pm-cockpit-test-env` — instance karl-agent de TEST pour un ticket cockpit
- `pm-core-update` — met à jour le code déployé de l'instance PM et le re-verrouille
- `pm-doctor` — Vérifie la cohérence des données PM
- `pm-engine-install` — installe, met à jour et teste les moteurs d'agents et les serveurs de m…
- `pm-hooks-install` — (ré)installe le hook git post-commit (report conso auto → Redmine,
- `pm-meta-migrate` — sépare la donnée machine (meta.yml) de la prose (overview.md). RM1994.
- `pm-perms` — applique/répare le modèle de perms multi-user PM
- `pm-resolver-flip` — bascule du résolveur PM vers les workspaces co-localisés.
- `pm-site-test` — Harnais de test / non-régression d'un site
- `pm-tags-audit` — écarts entre le CF Redmine « Tags », le registre et les usages.
- `pm-test` — mmi-pm test — lance la suite de tests hors ligne du système PM
- `pm-zfs-backup` — snapshots ZFS de la machine, au fil de l'eau

### Divers

- `pm-bus-drain` — exécute les abonnements des modules sur les événements en attente
- `pm-corehist-backfill` — réinjecte le VRAI historique git dans les repos -core.
- `pm-llm-models` — ce qu'un fournisseur LLM sert VRAIMENT, demandé au fournisseur
- `pm-module` — les modules de PM : lister, décrire, contrôler, mesurer l'écart
- `pm-release-watch` — la veille des publications qu'on attend
- `pm-searchdb` — l'index de requêtage de karl-PM
- `pm-stores-migrate` — ramène les stores de session du HOME vers le `var/` du repo PM. RM2992.
- `pm-token-check` — surveille la péremption des PAT GitLab de karl, rote à J-seuil
- `pm-workflow-sync` — Synchronise le workflow Redmine (transitions de statut) vers une
- `pm-worklog-merge` — reprendre un worklog de session resté à l'ancien emplacement

## Bibliothèques (importées, pas lancées)

- `pm_bus` — le journal des événements MÉTIER de PM
- `pm_cf_mirror` — miroir « champ frontmatter ↔ custom field Redmine »
- `pm_client_notify` — cœur de la notification client à la MEP
- `pm_concurrent` — qui travaille DÉJÀ sur ce ticket. RM3086 (lot L3 de RM3015).
- `pm_contacts` — l'annuaire de contacts, cœur partagé
- `pm_doc` — interface DocProvider (gestionnaire de docs agnostique) + backend wiki…
- `pm_engine_recipes` — le CATALOGUE des moteurs et des serveurs de modèles installables
- `pm_events` — prévenir le cockpit qu'une donnée a changé
- `pm_forge` — abstraction de forge git (GitLab / Gogs / GitHub) — RM2498 (T2).
- `pm_git` — auto-commit + push atomiques des écritures des scripts pm-*
- `pm_hierarchy` — Helpers partagés pour la hiérarchie parent/enfant des tâches PM.
- `pm_index` — l'INDEX des projets PM : les symlinks `projects/clients/<c>/projects/<p…
- `pm_license` — la licence d'un projet / d'un dépôt, posée à la naissance
- `pm_llm_call` — un appel de complétion à un fournisseur du registre
- `pm_llm_services` — les fournisseurs de modèles connus, prêts à déclarer
- `pm_lock` — verrous PAR RESSOURCE (flock) + écriture atomique
- `pm_log` — journal structuré du système PM et de karl-agent
- `pm_mail_routing` — de l'expéditeur d'un email au couple client/projet
- `pm_markdown` — Utilitaires markdown partagés par l'outillage PM
- `pm_modules` — le registre des MODULES de PM
- `pm_monitor` — les OBSERVATEURS du parc, en lecture
- `pm_norms_anchors` — ce qui doit survivre à une réécriture dense des normes
- `pm_notify` — le fil de notifications de l'instance
- `pm_output` — contrat de sortie des scripts PM
- `pm_partner` — liens vers les tickets d'un gestionnaire PARTENAIRE (N0, RM2654).
- `pm_paths` — Résolution de chemins du système PM iprospective.
- `pm_proclive` — « une session d'agent tourne-t-elle encore sur ce sid ? ». RM2810.
- `pm_provider_types` — le CATALOGUE des types de fournisseurs
- `pm_registry` — registre de serveurs (instances) + résolution d'instance par projet.
- `pm_reporting` — ledger annexe des données de reporting d'un ticket
- `pm_repos` — manifeste `repos[]` d'un projet PM : transport, identité, rattachement.
- `pm_roles` — quel rôle d'agent pour ce ticket ?
- `pm_scope` — garde de PÉRIMÈTRE des outils PM mutants
- `pm_searchdb` — l'index de REQUÊTAGE de karl-PM : une PROJECTION du Markdown
- `pm_secrets` — abstraction de gestionnaire de secrets (vault) — RM2681 (L0).
- `pm_session` — Id de session court (entier incrémental) + registre des branches/worktr…
- `pm_session_hook` — Reflète une création / transition de ticket PM dans le worklog de sessi…
- `pm_stores` — où vivent les données de SESSION, résolu une seule fois. RM3085 (lot L5…
- `pm_tags` — étiquettes de ticket
- `pm_task` — interface TaskProvider (gestionnaire de tickets agnostique) + backend R…
- `pm_task_log` — écrire dans le `.log.md` d'un ticket. Une seule fois. RM3085 (lot L5 de…
- `pm_task_md` — gabarit d'une fiche de tâche PM (frontmatter + corps + journal).
- `pm_think` — le fichier de réflexion d'un ticket (`RM<id>_<slug>.think.md`) et sa fu…
- `pm_timesheet` — reconstitution du temps de travail HUMAIN à partir des traces d'agents
- `pm_transcript` — lecture typée d'un transcript claude (JSONL). RM2305.
- `pm_worklog_states` — comment un worklog de session CLASSE ce qu'il porte. RM3085 (lot L5 de…
- `pm_ws_skeleton` — pont vers le verbe privilégié `pm-env-helper ws-init`
