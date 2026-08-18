# Changelog système

Évolutions du système de gestion de tâches dans son ensemble.
Pour les évolutions du schéma des tâches, voir [norms/CHANGELOG.md](norms/CHANGELOG.md).

Format : [Keep a Changelog](https://keepachangelog.com/fr/)

> Ce fichier consigne les **jalons système** (architecture, outillage, surface
> d'usage). Le détail vit dans les tickets `pm-ai-agents` ; les évolutions des
> normes dans `norms/CHANGELOG.md` (versionnées indépendamment, cf. `norms/VERSION`).

---

## [Unreleased] — Cockpit & environnements de test

### Outillage
- **`pm-env-session teardown` se bloquait sur son propre canari** (RM2679) : la garde
  « worktree sale » exemptait bien les artefacts posés par `create` (`.user.ini`,
  `pm-env.txt`), mais en **comparant des chaînes concaténées**. Avec `docroot: "."` —
  tout projet servi depuis la racine du checkout, dont `pisceen/presta` — elle
  produisait `?? ./pm-env.txt` là où `git status` écrit `?? pm-env.txt` : l'exemption
  ne matchait **jamais**. Comme l'échec du teardown est annoncé « non bloquant », il
  passait inaperçu et les worktrees (228 Mo pièce) s'accumulaient avec leur vhost.
  La comparaison porte désormais sur des **chemins normalisés** et gère les chemins
  quotés et les renommages.
- **`runtime.teardown_ignore`** (RM2679) : le projet peut déclarer les chemins **non
  suivis** que son appli écrit au runtime (ex. `yaml/*.php`, le cache de config de
  PrestaShop) — motifs fnmatch relatifs au worktree. Choix assumé de ne PAS passer la
  garde en `--porcelain -uno` : un fichier neuf qu'on a oublié d'ajouter doit continuer
  à bloquer le teardown. Un fichier **suivi et modifié** n'est jamais rendu jetable,
  même s'il correspond à un motif.
- **`pm-repo-new`** (RM2640) : le PM outillait la vie d'un dépôt mais pas sa **naissance** —
  créer un projet se faisait à l'UI ou au `curl`, exactement le cas visé par le tripwire #1.
  La commande enchaîne désormais résolution du groupe **par chemin exact** (tripwire #14,
  jamais par basename : incidents RM2219/RM2410), refus si le projet existe, `POST /projects`
  (**privé par défaut**, `default_branch` explicite), `--push-from` d'un dépôt local avec
  remote en **alias SSH canonique `gitlab:`** (jamais HTTPS, RM2328), puis `pm-protect`
  **appelé** et non réimplémenté. `--porcelain` sort `<id> <path_with_namespace>` : aucun id
  n'est deviné ni recopié de mémoire (tripwire #13). `--dry-run` montre la séquence complète.
  Passe par `pm_forge` — GitLab n'est pas codé en dur.

### Cockpit
- **Onglets épinglés du panneau central** (RM2672) : une vue ouverte (session, fiche de
  ticket, fiche projet, création) devient un onglet. **Un seul onglet non épinglé à la
  fois** — la vue suivante le remplace ; épingler le conserve. Les épinglés survivent au
  rechargement (une session n'est jamais rattachée d'office au boot). Le rail gauche
  reste la liste de référence : l'onglet est un marque-page, pas l'annuaire de sessions
  retiré en RM2140/2283. Nouvelle vue **＋ créer un ticket** en pleine page, avec les
  champs que la carte repliée ne portait pas (passe agent-testeur, env cible, estimation,
  difficulté) — validés côté serveur.
- **Panneau « 📧 emails »** (RM2671, chantier RM2666) : la file de triage devient
  cliquable — relever, router, rédiger, **créer à la validation**, rattacher à un fil
  existant, reclasser (la correction est apprise) ou écarter avec un motif. Le corps
  d'un email n'est chargé qu'au dépliage, jamais dans la liste. Le panneau ne
  réimplémente rien : il lit `/mail/queue` et délègue chaque geste au script du
  pipeline (argv strict, allowlist). `--mark-seen` n'est **pas** exposé : marquer lu
  agit sur une boîte de production, ça reste un geste CLI. Aide dédiée : page
  « Emails ».
- **Correctif — lancer une session non-claude** (RM2691) : `POST /spawn` avec
  `engine` = `shell`, `opencode` ou `vibe` répondait **500** (`UnboundLocalError`
  sur `joined`, affecté seulement dans la branche claude) alors que la session
  tmux était bien créée — l'appelant relançait et se prenait un 409 « session
  déjà active ». La réponse dit maintenant explicitement que le jeu de sessions
  n'a pas été rejoint (`reason: "sans-session-id"`) : sans set-at-launch, une
  entrée de jeu serait hollow (ni engine, ni session_id, ni cwd), donc non
  relançable, tout en consommant un slot du plafond.
- **Plafond mémoire des sessions** (RM2690) : chaque session tmux naît avec un
  plafond sur sa **scope systemd** (`MemoryHigh=6G` / `MemoryMax=8G` par défaut) —
  une session qui fuit se fait tuer **seule** au lieu de saturer la workstation et
  de laisser le kernel choisir la victime (incident OOM du 2026-08-13 : 15,7 Go de
  RSS, victime arbitraire). L'UUID de scope étant aléatoire, aucun drop-in
  déclaratif n'est possible : l'accroche est le spawn (couvre `/spawn` **et**
  `/resume`), jamais bloquante (systemd absent, délégation `memory` manquante ou
  `set-property` en échec → warning, session créée). **Réglable depuis le cockpit**
  (🔧 réglages, rubrique « Sessions », en GiB, `0` = illimité) via
  `sessions.memory_{high,max,swap}_gib` de `pm.config.yml` ; `KARL_AGENT_MEM_HIGH`
  / `_MAX` / `_SWAP` (`.env`, syntaxe systemd) **figent** la valeur — le champ est
  alors marqué 🔒 et l'écriture refusée. Ne s'applique qu'aux sessions créées
  ensuite. Le **swap est plafonné à 0** par défaut (`MemorySwapMax`) : sans lui,
  une session qui fuit grimpe lentement de `MemoryHigh` à `MemoryMax` en saturant
  le swap — et c'est le swap saturé qui fait ramer le poste. Convention inversée
  sur ce champ : `0` = aucun swap, `-1` = illimité.
- **Aide intégrée** (RM2593) : menu **❓ aide** + boutons `?` contextuels par
  panneau, ouvrant des pages de doc utilisateur markdown versionnées
  (`deploy/karl-agent/cockpit/help/`) servies par karl-agent (`/help`,
  `/help/<topic>`) et rendues dans le cockpit. Maintenues au fil des devs.
- **Instances cockpit de test relançables en un clic** (RM2588) : la file « à
  tester » sonde l'instance HTTPS (`/health`), affiche son état ●/⚠ + lien
  `https`, et expose « 🚀 (re)lancer » quand elle est down (survit aux reboots).

### Environnements de test
- **Exposition HTTPS des instances cockpit de test** (RM2565) : vhost karl
  factorisé (source unique `karl-vhost-render.sh`, non-régression `karl.conf`),
  réutilisé par `pm-cockpit-test-env` via `pm-env-helper vhost-karl-add` —
  terminal (wss) et micro (getUserMedia) fonctionnels en contexte sécurisé.

### Outillage
- **Worklog de session : les tickets sont groupés par projet** (RM2724). Le projet
  n'apparaissait qu'en suffixe de ligne (`_(pisceen-presta)_`), en queue d'une ligne
  qui porte déjà statut, référence, titre, dérive et commit — invisible dès que la
  session mélange plusieurs projets, ce qui est le cas normal. Il devient un
  **sous-titre de groupe** dans chacune des trois sections (*Reste à faire*, *En
  attente*, *Fait*), et le suffixe disparaît. Le regroupement est un rendu, pas un
  tri : l'ordre des items dans un groupe reste celui de la session, celui des groupes
  suit leur première apparition — sauf `hors projet`, qui ferme la marche. Un item
  ouvert **sans `--project`** n'est plus orphelin : son projet est rattrapé depuis le
  chemin de la tâche résolue par `resolve_live`. Au passage, un item dont le label ne
  fait que répéter sa référence affiche enfin le titre de la tâche (« RM2680 — RM2680 »).
- **Notifications de session : une notification traitée quitte le backlog**
  (RM2715, NORMS v1.71.0). Le canal `notify` (RM2466) n'avait que deux états —
  *au backlog* ou *effacée* : une notification consignée « ticket à ouvrir »
  restait affichée telle quelle après l'ouverture, la livraison ET la MEP du
  ticket, sa consigne devenue fausse. Elle porte désormais sa résolution
  (`notify --resolve <n> --ticket RM<id> [--note …]`) : elle sort du backlog
  **sans sortir du store** et descend dans une section d'archive avec le ticket
  qui l'a portée — modèle déjà posé par `mr_pending` (RM2583) et le registre des
  demandes (RM2621). `--clear` cesse d'être le geste par défaut : il DÉTRUIT, et
  ne vide plus que l'archive (ni les ouvertes ni les `critical` sans `--all`).
  Le rognage du canal sacrifie l'archive avant les notifications encore ouvertes.
  Côté **cockpit** (onglet état), seules les ouvertes sont servies, avec un
  rappel discret du nombre de traitées.
- **La doc ne suppose plus un vault unique** (RM2710, lot L4 du chantier RM2662) :
  NORMS `environments` § « Gestion des secrets » (**v1.70.0**) décrit des vaults
  **déclarés** — instances du registre providers, slug, défaut, surcharge
  client/projet, identifiants par dev — et les trois formes d'URI, dont
  `vaultwarden://` **toujours valide** ; tripwire 11 du KERNEL généralisé (« le
  secret de déverrouillage », pas « le master password Vaultwarden »). Suivent les
  templates (aspect `environments`, bootstrap secrets et environnements), les skills
  (`mmi-env-sync`, `mmi-pm-karl-mail-send`), `karl-mail-send.py`, et
  `tools/synchro`, qui **refusait** les nouvelles formes d'URI (`case
  vaultwarden://*` — un `secret://…` dans `MYSQL_ADMIN_SECRET` mourait en « URI
  invalide »). Le contrôle d'environnement du cockpit liste désormais **une ligne
  par instance de vault déclarée** avec les *noms* des identifiants trouvés, au lieu
  de guetter trois variables `BW_*` en dur — et ne rend plus muet un poste dont le
  `.env` d'instance est illisible (cas d'un worktree ou d'une instance de test).
  Deux gardes ajoutées au test : aucune **valeur** d'identifiant présente dans
  l'environnement ne doit apparaître dans le rapport (l'ancien test ne cherchait
  qu'un motif de nom, il serait passé sur un secret affiché en clair), et une ligne
  par instance déclarée. L'identifiant du template `001-secrets-vaultwarden` est
  volontairement conservé : c'est la clé référencée par les `bootstrap.skip` des
  projets, le renommer les ferait re-proposer.
- **Backend KeePass** (RM2684, lot L3a du chantier RM2662) : un fichier `.kdbx`
  et une passphrase suffisent — aucun serveur, aucun compte à créer. C'est le
  backend qu'un intervenant externe peut fournir sans rien installer côté
  iProspective, et la preuve que l'abstraction de L0 tient. Déclaration
  `{ axis: secret, type: keepass, file: "~/vaults/ipro.kdbx" }` (ou
  `SECRET__<SLUG>__FILE` / `__KEYFILE` par dev) ; déverrouillage
  `unlock-vault.sh -i <instance>`, qui pousse la passphrase au daemon **et vérifie
  aussitôt qu'elle ouvre la base** — sinon l'échec ne se verrait qu'à la première
  résolution, longtemps après la saisie. Le chemin d'un secret suit les groupes
  KeePass (`secret://kdbx-perso/clients/acme/prod-db`), le chemin donné valant
  **suffixe** du groupe réel. Dépendance **optionnelle** : sans `pykeepass`
  (`sudo apt install python3-pykeepass`), l'instance se déclare `unreachable` avec
  la commande d'installation, sans gêner les autres vaults. Diagnostics ordonnés
  comme on les corrige : configuration → dépendance → déverrouillage.
  `pm-providers.py instance <slug> [--field …]` expose la fiche d'une instance
  (c'est ce qui permet aux scripts shell de connaître le type d'un vault).
  Corrigé au passage : le flux Vaultwarden posait sa session **sans slug**, donc
  `unlock-vault.sh -i <autre-instance>` aurait déverrouillé l'instance par défaut
  — le bon jeton dans le mauvais coffre.
- **Plusieurs vaults déverrouillés en parallèle** (RM2683, lot L2 du chantier
  RM2662). `vault-agentd` tenait **une** session ; il tient désormais un **état par
  instance** (session, horodatages, backend), donc des TTL et des verrous
  indépendants : déverrouiller le vault d'un client ne prolonge pas celui
  d'iProspective, et son expiration ne le verrouille pas. Le daemon ne quitte que
  lorsqu'il ne reste plus aucune instance ouverte — comportement d'origine dès lors
  qu'il n'y en a qu'une. Protocole étendu, **rétrocompatible** (un appel sans slug
  vise l'instance par défaut) : `SET-SESSION [<slug>] <token>`, `LOCK [<slug>]`,
  `SYNC [<slug>]`, `LIST-IN <slug> [filtre]`, et `STATUS <slug>` qui garde le format
  historique tandis que `STATUS` nu devient un tableau de bord `<slug>\t<état>`.
  Côté scripts : `unlock-vault.sh -i <instance>` (+ `--print-instance` pour
  diagnostiquer sans rien déverrouiller), `lock-vault.sh [<instance>]`,
  `vault-list.sh -i <instance>`. Le type de chaque instance vient du registre
  providers ; **sans registre lisible, le daemon dégrade** vers l'instance unique
  au lieu de tomber — un `sys.exit()` de `PMConfig.load()` (qui ne dérive pas
  d'`Exception`) tuait sinon le thread de service et le client recevait un silence.
  Corrigé au passage : la convention de nommage des identifiants par instance
  devient `SECRET__<SLUG>__…` avec slug **normalisé** (`vw-ipro` → `VW_IPRO`) — la
  forme à tiret n'était pas un nom de variable shell valide, donc inutilisable
  depuis un `.env` sourcé ; la forme littérale reste lue par tolérance.
- **Vaults déclarés en conf, par client ou par projet** (RM2682, lot L1 du
  chantier RM2662). Le registre providers gagne un **axe `secret`** : chaque vault
  est une instance nommée (`providers.servers.<slug>`, sans aucun secret dedans),
  avec un défaut (`providers.defaults.secret: vw-ipro`, qui reproduit l'existant).
  Deux limites du registre tombent au passage, au bénéfice de **tous** les axes :
  la liste d'axes devient **déclarative** (`providers.axes`) — un axe futur
  (monitoring/Zabbix) ne coûte plus qu'une ligne de conf —, et la résolution gagne
  le **niveau client** : `resolve_instance(project_meta, axis, registry,
  client_meta=…)` applique projet > legacy projet > **client** > défaut, ce qui
  permet « tous les projets de ce client passent par tel vault ». Sans
  `client_meta`, la résolution est identique à avant (prouvé par test). Les
  identifiants restent **par dev** : `SECRET__<slug>__CLIENTID` / `__FILE` /
  `__TOKEN` dans `~/.config/mmi-pm/.env` (convention RM2546), avec repli sur les
  variables historiques tant qu'un dev n'a pas migré ; `pm-providers.py resolve`
  affiche l'instance retenue et les **noms** des identifiants trouvés, jamais leurs
  valeurs. Corrigé au passage : `pm-providers resolve --client X` se laissait
  écraser par la détection du cwd et répondait pour le projet courant.
- **Socle multi-vault : `pm_secrets`** (RM2681, lot L0 du chantier RM2662). La
  résolution de secrets passe derrière une interface `SecretBackend` (statut,
  résolution, listing, `Capabilities`) avec des erreurs normalisées
  (`locked` / `unreachable` / `not_found` / `denied` / `bad_uri` / `unsupported`) ;
  `VaultwardenBackend` est l'**extraction iso-comportement** de l'existant, et
  `vault-agentd` ne fait plus que porter la session et le protocole. Trois formes
  d'URI acceptées : `secret://<instance>/<chemin…>[#champ]`, `secret:<chemin…>` et
  la forme historique `vaultwarden://<org>/<coll>/<item>` — **supportée
  définitivement**, aucun pointeur existant à réécrire. Un URI visant une instance
  autre que celle servie est **refusé explicitement** plutôt que résolu en silence
  dans le mauvais coffre (multi-instances : RM2683). Point d'extension
  `register_backend()` pour les backends suivants (KeePass RM2684, 1Password,
  Nextcloud Passwords, sops). Non-régression prouvée par un harnais qui rejoue
  l'ancienne et la nouvelle implémentation sur un faux `bw`
  (`test_vault_agentd_isocomportement.py`, comparaison stricte des réponses
  nominales + codes de sortie de `resolve-secret.sh`).
- **Contacts clients : nom, prénom, email, téléphone** (RM2702) :
  `pm-client-contact.py` (`add` / `list` / `set` / `remove` / `mark-internal` /
  `import-redmine`) devient le seul point d'écriture de `contacts[]` dans le
  `meta.yml` du client, au schéma `last_name` / `first_name` / `email` / `phone` /
  `role`. `internal: true` marque **nos** adresses — le gabarit de création en pose
  une chez chaque client, elle n'identifie donc personne (et a failli servir à router
  du courrier entrant, RM2669). `import-redmine` amorce la fiche depuis les comptes
  Redmine rattachés aux projets du client (nom, prénom, email y sont déjà ; le
  téléphone reste à saisir). Documenté dans NORMS (`structure-reference`, **v1.69.0**).
  Cockpit : catégorie *contacts*, et les arguments `const` du catalogue acceptent
  désormais une **sous-commande positionnelle**. Un **annuaire indépendant des
  clients** (une personne, plusieurs rattachements) est à l'étude — RM2703.
- **De l'email au ticket, à la validation** (RM2670, chantier RM2666) :
  `karl-mail-draft.py` rédige une proposition de ticket depuis un email de la file
  (`claude -p` sans outils, JSON strict, projet **choisi dans une liste fournie** —
  jamais inventé), puis crée le ticket **quand un humain valide** (`--create`), en
  journalisant le `Message-ID` d'origine dans la description. Un email qui répond à un
  fil pose une **note** au lieu d'ouvrir un doublon — y compris quand le sujet a perdu
  son marqueur `[RM<id>]` (`--note-on`). Par défaut, seuls sujet, expéditeur et
  500 premiers caractères partent au modèle ; `--full-body` reste un choix explicite.
  Cockpit : `mail-draft` / `mail-show` / `mail-create` / `mail-dismiss`.
- **Relève des emails de karl** (RM2668, chantier RM2666) :
  `scripts/karl-mail-fetch.py` ouvre enfin la **lecture** de la boîte
  `karl@iprospective.fr` (RM1723 était *send-only*) et dépose les messages humains
  dans une **file de triage** locale — hors git, le repo de données partant sur
  GitLab. Les dossiers classés côté serveur sont relevés en premier, **`INBOX`
  ensuite** (un correspondant inconnu du carnet n'est classé nulle part). Lecture
  **non destructive** (`BODY.PEEK`, pas de DELETE/MOVE, `--mark-seen` opt-in),
  **idempotente** (index des `Message-ID`), robots et listes écartés. Exposé au
  cockpit via le catalogue de commandes (catégorie *mail*), qui gagne au passage
  les arguments **`const`** — un flag imposé par le catalogue, ni affiché ni
  négociable côté client. Défauts calés sur la boîte réelle : `INBOX.Clients` est
  de confiance, `INBOX.Gitlab` / `INBOX.Vault` jamais relevés.
- **Routage des emails entrants → client/projet** (RM2669, chantier RM2666) :
  `karl-mail-route.py` + `pm_mail_routing.py` proposent, pour chaque email de la
  file, un client et — seulement quand c'est certain — un projet, avec **confiance
  et source** : fil `[RM<id>]`, table apprise `mail-routing.yml`, compte Redmine de
  l'expéditeur, `contacts[]` du client, indice textuel. Sinon l'email reste « à
  classer » — jamais de choix silencieux entre deux candidats (tripwire 14). Chaque
  correction humaine est **apprise** ; apprendre le *domaine* d'un fournisseur grand
  public (gmail, orange…) est refusé, et les adresses maison sont exclues des
  indices — sans quoi tout mail de Mathieu partirait chez un client au hasard,
  `contacts[]` portant la même adresse propriétaire chez les 20 clients.
- **Instances cockpit de test : les commandes ⚙ fonctionnent enfin** (RM2668) :
  `pm-cockpit-test-env` transmet `PM_CORE_DIR` à l'instance. Sans lui, le worktree
  de code n'a pas de `.env` et **toute** commande du catalogue mourait en rc=1
  (« aucun .env trouvé ») — `conso-report` comme les nouvelles commandes mail.
- **MR sans ticket** (RM2644) : `pm-mr create --no-ticket --title "…"` ouvre une MR
  pour un changement qui n'a pas de ticket — ajout d'un terme au glossaire du
  cockpit, coquille (cf. NORMS `governance` § « Changements sans ticket », v1.68.0).
  La **MR reste due** : les branches d'intégration et de prod sont protégées, « sans
  ticket » n'est pas « push direct » ; seules tombent les accroches au ticket (CF
  *GIT Branche* / *GIT PR*, `git.mr_urls`, `--status`). Le mode exige un titre,
  refuse un `rm_id` simultané et **refuse une branche préfixée `<id>-`** — elle y
  trahirait un ticket oublié. Comble le trou qui avait obligé à créer la MR du terme
  « one-off » à la main par l'API.
- **Env de session : plus de saut ssh inutile, plus de base périmée** (RM2646).
  Deux défauts de `pm-env-session`, constatés en prenant un ticket depuis le
  conteneur `dev` : (1) le helper privilégié était **toujours** appelé via
  `ssh <env_runtime.ssh_host>`, donc la box tentait de se joindre elle-même et
  échouait — « non bloquant », donc **le vhost n'était jamais posé sans que rien
  ne le dise** ; il s'exécute désormais en local (`sudo -n`) dès que le binaire
  helper est présent et exécutable, `env_runtime.force_ssh: true` rétablissant
  l'ancien comportement. (2) `resolve_base()` retenait le ref **local** de la
  branche d'intégration même périmé (vu : `refs/heads/dev` à ~200 commits de
  retard) et créait les branches de ticket sur du vieux code ; le garde de
  `pm-branch-start` (RM2574) est factorisé dans `pm_git.resolve_base_ref` et
  partagé par les deux outils — il ne pouvait pas rester d'un seul côté.
- **Clôture de ticket robuste** (RM2587) : le hook worklog de session
  (`pm-task-status-update`, étape 7) est best-effort — un checkout sans
  `pm_session_hook.py` ne casse plus la clôture ni l'auto-commit.
- **GC des envs de tickets fermés** (RM2566) : `pm-env-gc` / `mmi-pm env gc`
  retire les worktrees `envs/` dont le ticket est `ferme`, **propres** et
  **intégrés** (HEAD ancêtre de `origin/main`/`origin/dev`), et élague leurs
  branches locales en merge-safe. Dry-run par défaut ; saute tout worktree sale
  ou non intégré. (Comble l'absence de nettoyage périodique ; le bug de nommage
  qui produisait les slugs à rallonge était déjà corrigé, RM2523.)

### Documentation
- **Point d'entrée développeur** (RM2594) : `DEVELOPMENT.md` relie README,
  normes, `knowledge/` et `docs/` (architecture, flux, boucle de dev « comment
  contribuer »), référencé depuis le README. Pointe les sources vivantes, sans
  valeur qui rouille.

### Gouvernance
- **Contrat « docs vivantes » étendu à 4 cibles** (RM2595, NORMS v1.67.0) : la
  section dédiée « Développement du PM » (module `governance`) impose de mettre à
  jour, dans la même MR, la doc correspondant à la surface changée — `Changelog.md`,
  `README.md`, **aide cockpit** et **`DEVELOPMENT.md`** — avec déclencheur KERNEL
  « je livre un changement de surface ».

---

## [1.12.1] - 2026-07-20 — Garde de cible pm-branch-start

### Outillage
- **`pm-branch-start` refuse un CORE comme cible de branche de code** (RM2360). La
  cible n'était validée que contre `projects_root` (blocklist de taille 1) : lancé
  depuis la racine d'un workspace projet — le core, porteur de `.mmi-pm` — le script
  branchait le core au lieu du repo de code (bug RM2325). Garde structurelle : un repo
  qui **révisionne `.mmi-pm`** (`git ls-files`) est un core → refus avec message
  actionnable (le code se branche dans un worktree `envs/` tiré de `repos/`). S'appuie
  sur l'invariant NORMS 1.58.0 (structure-reference, RM2348). Cross-check ajouté : un
  cwd pointant sur un repo ≠ `git.repo` enregistré est refusé (contournable par `--repo`
  explicite). Tests : `test_pm_branch_start_guard.py`.

### Gouvernance documentaire
- Règle « **docs vivantes du repo PM** » (module governance, NORMS v1.54.0) :
  `Changelog.md` alimenté **dans la même MR** que toute livraison qui change la
  surface du système ; README sans valeurs qui rouillent (RM2250).

### Cockpit karl (web-UI, `karl.iprospective.fr`)
- **Backend de sessions** `karl-agent` (RM1771) : superviseur tmux d'agents
  (spawn/send/kill/capture), reprise de session (RM1939), nommage ticket ou slug
  (RM2144), unit systemd **user** dans le conteneur dev.
- **Front v0 → v0.1** : lanceur + attach navigateur (RM1873), ergonomie de
  supervision — prompts, chips skills, moniteurs multi-panes (RM1893), onglets
  groupés par projet + badge d'attention (RM2140), encart session en direct
  (branches/worktrees du registre pm_session, RM2166) restructuré multi-tickets
  (RM2173), copier/coller fiable ttyd (RM2168), choix moteur/modèle (RM1921,
  RM1941). Auth user/mdp + exposition publique (RM2139, spike RM1803).
- **Command-catalog déclaratif** (chapeau RM2203) : `GET /pm/commands` +
  runner générique allowlisté `POST /pm/run` (RM2209), menus/formulaires
  auto-générés (RM2211), menu Nouveau projet/client (RM2212), menu Réglages —
  édition contrôlée de pm.config/pm.pricing (RM2213).
- **Console de test / revue** (RM2210) : file `a_tester_*` enchaînable en
  onglets 🧪, déploiement d'env de session (choix clone BDD), verdicts
  valider/MEP/renvoyer ; déploiement vers l'env de test PARTAGÉ (`pm-env-deploy`,
  RM2218) ; **sonde de vivacité** des envs (canari `pm-env.txt`), fiche ticket
  riche avec **protocole de test** en évidence (RM2229).

### Boucle de recette outillée (RM2229)
- CF Redmine 30 « **Protocole de test** » (texte long) + miroir frontmatter
  `test_protocol`, outil `pm-task-protocol` (--set/--append, rédaction **au fil
  de l'eau**), garde-fou à la livraison ; `pm-env-session` tient `test_url`
  (frontmatter + CF 14) : create écrit, teardown vide ; étapes `post_create`
  déclaratives du manifeste (vendor, assets… — create = « réparer »).
  NORMS v1.53.0.

### Fiabilité outillage
- **Garde de périmètre projet** sur les 5 outils PM mutants (RM2274) : refus
  d'écrire sur un ticket d'un autre projet si l'id n'a jamais été vu dans la
  session (empreinte d'un id prédit, tripwire #13) ; `--cross-project` pour
  l'assumer. Complète les gardes code (RM2224/RM2240) côté écritures Redmine/MD.
- Fin de la prédiction d'ids : tripwire NORMS + `pm-task-add --porcelain`
  (RM2170), gardes `pm-mr` branche≠id + verbe atomique (RM2224), anti-prédiction
  d'iid de MR (RM2232), résolution de projet par path complet — fin de la fuite
  inter-clients (RM2219) ; `redmine-post-note` diagnostique les relations
  bloquantes au lieu de conclure « permissions » (RM2222) ;
  `pm-workspace-coloc` : alias PM_CLIENTS (RM2216) ; `pm-task-add` description
  multi-ligne (RM2003) ; `pm-project-new` crée le volet PM co-localisé (RM2228).

## [1.11.0] - 2026-07-08 — Privsep, instances, métriques

### Privilèges séparés & instances
- Code du core **root-owned** verrouillé par `core-lock` (RM2032), périmètre
  `var/` préservé aux updates (RM2056), migration `docs/` + refactor scripts
  (étape 0, RM2043) ; installeur complet d'instance `install-mmi-pm` + alias
  `mmi-pm` sur le PATH (RM2062) ; multiplexing SSH du `core update` — une
  connexion au lieu de N (RM2069).
- Outils de recâblage : `pm-gitlab-rename` (RM1983), `pm-session-relocate`
  (RM1989), remotes re-câblés après promotion des groupes GitLab (RM1992) ;
  détection projet via cwd dans les workspaces co-localisés (RM2095, RM2120).

### Métriques temps/tokens → Redmine
- Push des métriques par ticket : estimation + delta par commit (RM1806,
  réconcilié RM1825), reporting v2 split input/output idempotent (RM2048),
  auto-report post-commit / fin de session / clôture (RM2035), cron de
  rattrapage (RM2160), fix du sous-comptage du hook Stop (RM2161), tarifs
  Fable 5 / Opus 4.x dans `pm.pricing.yml` (RM2163/RM2164), ROI assisté
  (RM1717) ; garde anti-tick sur ticket fermé (RM2053).
- **Budget de contexte par rôle** : mesure + plafonds enforcés par le doctor
  (RM1943).

## [1.10.0] - 2026-06-29 — Discipline git & envs de session

- **Workflow 3 branches** dev → preprod → prod (RM2030), interdiction du commit
  direct sur branche protégée (NORMS RM2051) enforcée côté GitLab par
  `pm-protect` (RM2052) ; `pm-mr` — push + MR + CF + merge fiable avec poll de
  mergeabilité (RM1871, RM2055) ; `pm-branch-start` — branche par ticket +
  en_cours (RM1897).
- **Layout workspaces repos/+envs/** : migration des workspaces pré-norme
  (`pm-env-migrate`, RM2028, skill RM2159), ids de session courts + worktrees
  suivis (RM2034) ; **envs de session par ticket** `pm-env-session` (RM1834,
  hooks auto sur en_cours/ferme).
- Rotation auto des tokens GitLab à J-7 + vérif début de session
  (`pm-token-check`, RM2046) ; worklog de session auto-alimenté par hooks +
  statut live (RM2068) ; `norms/VERSION` + `pm-norms-changes` (RM2033) ;
  `pm-task-blockers` — diagnostic des transitions refusées (RM2066).

## [1.9.0] - 2026-06-12 — Gouvernance NORMS & rôles Redmine

- **NORMS factorisé** : KERNEL runtime (déclencheurs + tripwires) + modules à la
  demande + assemblage `pm-norms-assemble` / garde `pm-norms-doctor` (RM1922) ;
  skills `mmi-pm-*` migrés dans le repo et distribués cross-instance (RM1868) ;
  ledger de non-perte réconcilié (RM2070).
- **Rôles & attribution Redmine** : statut terminal unique « Fermé » + CF Raison
  (RM1742), Manager IA formalisé + cascade projet (RM1734), demandeur effectif
  via author (RM1735, migration RM1739), passe agent-testeur conditionnelle
  `requires_agent_test` (RM1879), statut d'entrée `nouveau` (RM1829), couplage
  statut+assignation (RM1752).
- Outillage : `pm-task-link` (RM1709), `pm-task-edit-desc` (RM1794),
  `redmine-config-check` (RM1807), stats PM (RM1865), `pm-wiki-sync` P1
  (RM1841), bot Telegram karl — spawn + injection conversationnelle
  (RM1775/RM1776), symlink workspace unifié `.mmi-pm` (RM1750), filtrage CF
  « IA » (RM1716).

---

## [1.8.0] - 2026-05-15

### Ajouté — Couche d'abstraction des chemins (`pm.config.yml` + `pm_paths.py`)
- Nouveau fichier `pm.config.yml` à la racine : tous les chemins du système
  (racines, entités, projets, tâches, symlinks) sont définis comme patterns
  paramétrables. Aucun chemin absolu local n'est commité (uniquement `${VAR}`
  depuis `.env`)
- Nouvelle lib `scripts/pm_paths.py` : `PMConfig.load()` + `cfg.path(...)` +
  itérateurs (`iter_entities`, `iter_projects`) + lookups Redmine
  (`find_task`, `find_project_by_redmine_id`)
- Support d'un `pm.config.local.yml` (gitignored) pour surcharge locale
- Permet de déplacer le repo PM, déplacer le repo projets, ou réorganiser la
  structure interne sans toucher au code ni à la doc — une seule ligne à
  modifier dans la config

### Modifié — Symlink workspace → PM caché (`.mmi-pm`)
- Renommage de `mmi-pm` → `.mmi-pm` dans les 2 workspaces concernés
  (`/zfs/workspaces/redmine`, `/zfs/workspaces/perso/mathematicians-db`)
- Convention portée par `paths.reverse_link` dans `pm.config.yml`

### Modifié — Refacto exhaustif scripts + doc
- 5 scripts refactorés pour passer par `PMConfig` : `pm-dashboard.py`,
  `redmine-fetch-task.py`, `redmine-fetch-updates.py`, `pm-project-bootstrap.py`
  (+ corrections docstrings `priority.py`, `validate-task.py`)
- Doc reformulée en patterns logiques (`paths.task_file`, `{entity_client_dir}`,
  …) : `CLAUDE.md`, `agents/worker-common.md`, `agents/orchestrateur.md`,
  `agents/summarizer.md`, `README.md`, `templates/bootstrap-tasks/002-git-repos.md`,
  `TODO/003-pm-cli.md`
- Plus aucun hardcode `projects_root / "clients"` ni `mmi-pm/...` dans le code
  ou la doc vivante

### Conventions
- NORMS v1.8.0 (minor bump) : `norms/CHANGELOG.md` détaille les évolutions ;
  snapshot v1.7.2 archivé dans `norms/archive/`

---

## [1.7.2] - 2026-05-15

### Ajouté
- NORMS § "Memberships par défaut sur nouveau projet Redmine" :
  groupe Admin (49) en Manager + groupe iProspective (70) en Intervenant

### Acté
- Bootstrap projet `clients/redmine/projects/redmine/` exécuté avec succès :
  tickets RM1661 (secrets), RM1662 (git-repos), RM1663 (environnements) créés
  côté Redmine + tâches MD générées + bootstrap.done rempli

---

## [1.7.1] - 2026-05-15

### Ajouté — Tâches de bootstrap projet
- 7 templates dans `templates/bootstrap-tasks/` (001-secrets, 002-git, 003-envs
  cochés par défaut ; 004-stack, 005-deployment, 006-testing, 007-monitoring
  optionnels)
- Section NORMS "Création d'un projet PM ↔ Redmine" + "Tâches de bootstrap"
- Frontmatter `project/overview.md` : champ `bootstrap.{skip,done}[]`
- Script `pm-project-bootstrap.py` à venir (commit suivant)

---

## [1.7.0] - 2026-05-14

### Ajouté — Environnements + gestion des secrets via Vaultwarden
- NORMS v1.7.0 (cf [norms/CHANGELOG.md](norms/CHANGELOG.md)) :
  - Aspect `environments.md` + énumération noms d'env standard
  - Tableau `env_vars[]` (noms + description, sans valeurs)
  - Convention `vaultwarden://<org>/<collection>/<item>` pour les secrets
  - Architecture vault : org iProspective + collections `<client>-agents` + user `karl@iprospective.fr` (read-only)
  - Task : nouveau champ `target_env`
- Scripts (4 nouveaux) :
  - `scripts/vault-agentd.py` — daemon local, session BW en mémoire, socket Unix
  - `scripts/unlock-vault.sh` — déverrouillage manuel (master password prompt)
  - `scripts/resolve-secret.sh` — résolution d'un secret par les agents
  - `scripts/lock-vault.sh` — verrouillage explicite
- Templates : `aspects/common/environments.md` créé ; `hosting.md` resserré
- `.env.example` étendu (VAULT_URL, BW_CLIENTID/SECRET, options d'expiration)

### Modifié
- `templates/task.md` bumped 1.5.2 → 1.7.0 + `target_env`

---

## [1.6.0] - 2026-05-14

### Ajouté — Types d'entités + partage cross-client + symlinks bidirectionnels + knowledge base
- NORMS v1.6.0 (cf [norms/CHANGELOG.md](norms/CHANGELOG.md)) :
  - `client.type` ∈ {`client`, `product`, `self`}
  - `project.used_by_clients[]` + `project.provided_by` (cross-client)
  - `clients/<c>/projects_used/` (symlinks générés, navigation humaine)
  - Symlink inverse `workspace` côté PM (en plus du `mmi-pm` existant côté workspace)
- `knowledge/` (knowledge base transverse, complémentaire à `security/knowledge/`) :
  - `knowledge/INDEX.md`
  - `knowledge/redmine/` : overview, api, gotchas, migration Textile→Markdown, script
- Clients créés : `iprospective` (type self), `redmine` (type product)
- Migration Textile → Markdown réussie sur l'instance Redmine interne `tasks.iprospective.fr` :
  6974 modèles convertis, 0 échec, procédure capitalisée

### Modifié
- `clients/lemathou/client/overview.md` bumped `schema_version: 1.6.0` + `type: self`
- `CLAUDE.md` : référence `knowledge/INDEX.md`, version 1.6.0

---

## [1.5.5] - 2026-05-13

### Ajouté
- `redmine-fetch-updates.py` : appende désormais chaque nouveau journal Redmine
  dans le `.log.md` de la tâche (persistance, conforme append-only NORMS)
- `redmine-post-note.py` : option `--attach <fichier>` (peut être répété) — upload
  les fichiers via `/uploads.json`, récupère les tokens, les associe au PUT issue
- NORMS § "Workflow multi-tour" : format de l'entrée log issue de Redmine documenté

### Acté
- Cycle multi-tour testé sur RM1658 :
  - User a posté remarques + repassé en a_corriger + réassigné à l'agent
  - Agent a détecté les nouveautés via fetch-updates, traité les 4 demandes,
    enrichi les 3 livrables, soumis avec les fichiers en pièces jointes

---

## [1.5.4] - 2026-05-13

### Ajouté
- `scripts/redmine-fetch-updates.py` — récupère les nouveaux journaux Redmine
  depuis `redmine_last_journal_id`, affiche notes + changements d'attributs,
  met à jour le frontmatter de la tâche
- `scripts/redmine-post-note.py --assign-to <id|author|me>` — réattribution
  manuelle ou automatique
- Auto-réattribution au demandeur sur `--norms-status a_tester_verifier`
- Vérification post-PUT étendue à `assigned_to_id` (warn + exit 2 si non appliqué)
- Schema 1.5.2 : champs `redmine_last_journal_id`, `redmine_last_checked_at`
- NORMS : section "Workflow multi-tour" + règle d'attribution Redmine

### Acté
- Workflow end-to-end testé sur RM1658 (création Redmine → fetch → traitement →
  livrables → soumission → réattribution au demandeur)

---

## [1.5.3] - 2026-05-12

### Ajouté — Intégration Redmine (premiers scripts)
- `scripts/redmine-test.py` — vérifie connexion API (URL, clé, projets accessibles, ticket spécifique)
- `scripts/redmine-fetch-task.py` — fetch un ticket Redmine, identifie le projet MD via `redmine.project_id`, génère le fichier de tâche conforme au schéma + journal initial, lance le validateur
  - Mapping `tracker` → `type` (bug→bugfix, feature→feature, support→assistance, etc.)
  - Mapping `priority` → `priority` (low/normal/high/urgent)
- `scripts/redmine-post-note.py` — poste une note (avec changement de statut optionnel) sur un ticket ; utilisé par les agents pour répondre

### Acté
- Connexion vérifiée : compte API = `claude-chefproj-1` (orchestrateur), projets `ai-agents` + `mathematicians-db` accessibles

---

## [1.5.2] - 2026-05-12

### Ajouté
- `scripts/pm-dashboard.py` — CLI dashboard du système (phase 0 de TODO 002)
  - Vue d'ensemble : clients, projets, tâches
  - Tableau des statuts par projet
  - Top ROI (tâches `a_faire` avec dépendances satisfaites)
  - Sections "En cours", "À tester", "À corriger" (affichées si non-vides)
  - Activité récente (5 derniers `.log.md` modifiés)
  - Utilise `rich` si disponible (rendu coloré), fallback ASCII sinon
  - Filtres : `--client <slug>`, `--top N`, `--activity N`
- TODO 002 phase 0 marquée comme réalisée

---

## [1.5.1] - 2026-05-12

### Modifié
- Symlink de cohabitation renommé : `.pm` → `mmi-pm` (évite conflit avec extension Perl, visible dans `ls`, préfixe cohérent avec les skills `mmi-*`)
- Symlink existant sur `mathematicians-db` renommé en place

---

## [1.5.0] - 2026-05-12

### Ajouté — Lien Redmine strict + symlink `.pm`
- Convention `.pm` : symlink dans chaque workspace projet vers le dossier PM centralisé
- Lien dur MD ↔ Redmine : `redmine_id` + cohérence filename, `redmine.project_id` obligatoire
- Validator étendu (`validate_redmine_coherence`)
- TODO 002 (interface de gestion + supervision) et TODO 003 (CLI `pm`) créés

### Modifié
- NORMS bumped 1.4.0 → 1.5.0
- Templates `task.md`, `project-overview.md`, `client-overview.md` mis à jour
- `worker-common.md` : résolution de chemins documentée
- PISTES.md : ajout de la piste « Création MD → Redmine » (sens inverse)

---

## [1.4.0] - 2026-04-27

### Ajouté — Cahier des charges multi-fichiers
- Structure `client/` et `project/` en dossiers (overview + aspects)
- 40 templates d'aspects par domaine : common, website, ecommerce, api, saas,
  mobile, data, legal
- Cascade aspect par aspect entre niveaux client et projet

### Modifié
- Templates renommés en `*-overview.md`
- Agents (worker-common, summarizer) mis à jour pour charger tout le dossier
- NORMS bumped 1.3.0 → 1.4.0

---

## [1.3.0] - 2026-04-27

### Ajouté — Multi-client / multi-projet hiérarchique
- Structure `clients/{C}/projects/{P}/tasks/` dans le repo projets
- Cascade contextuelle : client → projet → tâche, héritage avec override
- Fichiers auto-générés (Changelog, Pistes, Remarques) aux niveaux client et projet
- Section "Structure / Fonctionnement" enrichie automatiquement
- `agents/summarizer.md` : nouvel agent pour génération automatique
- `scripts/priority.py` : ordonnancement par ROI avec filtre dépendances
- `scripts/cron.example.sh` : exemple de configuration cron pour orchestrateur,
  summarizer, ranking ROI hebdomadaire
- `templates/client.md` : nouveau template client
- `templates/project.md` enrichi : client, defaults, stack (avec section tests),
  section Structure / Fonctionnement

### Modifié
- `agents/orchestrateur.md` : déclenchement par cron, scan multi-clients,
  référence à scripts/priority.py
- `agents/worker-common.md` : contexte chargé en cascade (4 niveaux)
- `CLAUDE.md` : invocation mise à jour avec client + projet
- `README.md` : workflow création client / projet / tâche
- NORMS bumped v1.2.1 → v1.3.0 (archive v1.2.1 créée)

---

## [1.2.5] - 2026-04-27

### Ajouté
- `scripts/validate-task.py` : validateur structurel (champs obligatoires,
  enums, transitions, cohérence status_history, conditional rules, completion_pct)
- `.gitlab-ci.yml` : pipeline CI exécutant la validation sur chaque push
- `templates/RM9999_exemple-tache-complete.md` : exemple complet et valide,
  utilisé par le CI comme cas de test
- Règle test-first dans `worker-dev.md` (test reproduisant le bug avant fix,
  tests des critères d'acceptation avant code)
- Obligation pour `reviewer.md` d'exécuter les tests (pas juste vérifier
  leur existence) — tout échec = rejet automatique
- `PISTES.md` : section "Tests — évolutions reportées" avec stack de tests
  dans templates/project.md, validation cross-fichiers, génération automatique
  de stubs depuis critères d'acceptation, tests workflow E2E

---

## [1.2.4] - 2026-04-27

### Ajouté
- `PISTES.md` : document de pistes d'évolution AI-natives pour une v3
  (branch & merge, critiques continus, décomposition asymétrique,
  pipeline Intent→Plan→Fan-out→Synthèse, exécution spéculative)
- Nouveaux rôles d'agents proposés : intent-extractor, adversary, critic, synthesizer

---

## [1.2.3] - 2026-04-27

### Ajouté
- `.env.example` : variables d'environnement requises (GitLab, Redmine, chemins)
- `projects/` gitignored : le dossier projects est désormais un repo git séparé,
  cloné indépendamment — le repo PM est publiable sans données de projets

### Modifié
- `.gitignore` : ajout de `.env` et `projects/`
- `norms/NORMS.md` v1.2.1 : config globale externalisée en variables d'environnement

---

## [1.2.2] - 2026-04-27

### Ajouté
- `CLAUDE.md` : bootstrap automatique pour Claude Code — orientation, ordre de lecture, rappels critiques
- `scripts/invoke.md` : guide d'invocation manuelle (workers, reviewer, orchestrateur, workflow complet)

---

## [1.2.1] - 2026-04-27

### Refactoring
- Extraction des règles communes des workers dans `agents/worker-common.md`
  (périmètre d'écriture, contexte, format journal, soumission, locking, blocage)
- Workers réécrits en version compacte : chaque fichier ne contient plus que
  ce qui est spécifique au rôle — taille réduite de ~50%

---

## [1.1.0] - 2026-04-27

### Ajouté
- Section collaboration multi-agents dans NORMS.md (rôles, règles d'écriture, protocoles)
- Section architecture de déploiement dans NORMS.md (V1, V1.5 NFS/ZFS, V2 Git/branches)
- `README.md` racine : guide d'utilisation humain et agent
- `agents/` : system prompts de référence pour orchestrateur, workers, reviewer
- `.gitignore`

### Modifié
- `CHANGELOG.md` racine : rempli et séparé du changelog de normes

---

## [1.0.0] - 2026-04-26

### Initial
- Structure de dossiers : `norms/`, `projects/`, `templates/`, `norms/archive/`
- `norms/NORMS.md` v1.0 : schéma frontmatter complet, machine d'états 7 statuts,
  valeurs énumérées, règles du journal append-only, versionning des normes
- `norms/CHANGELOG.md` au format Keep a Changelog
- `templates/task.md` : template tâche avec tous les champs
- `templates/project.md` : template projet
- Initialisation Git sur branche `dev`
