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
- **Aucun commit/push direct sur une branche protégée** (KERNEL #3) — vaut **dès le
  flux 2 branches** (`dev` + prod), pas seulement le flux 3 branches opt-in :
  l'intégration (`dev`) **et** la prod (`main`/`master`) ne reçoivent que des **merges
  de MR**. Même la **promotion `dev`→prod** passe par une MR (jamais un commit posé sur
  `main`). Un commit direct sur `main` court-circuite la promotion → divergences
  `dev`↔`main` et **collisions de version NORMS** (vécu : RM2035/2038/2048).
- **Enforcement GitLab — outil `pm-protect` (RM2052)** : `pm-protect [--repo PATH |
  --project-id N]` applique la **politique de protection standard** (idempotent,
  `allow_force_push=false`, branche absente ignorée), token *manager* :

  | Branche | Allowed to push | Allowed to merge |
  |---|---|---|
  | prod (`main`, ou `master` si elle existe) | **personne** | Maintainer |
  | intégration (`dev`) | **Maintainer** (restructuration assumée) | Maintainer |
  | `preprod` (flux 3 branches) | **personne** | Maintainer |

  `merge=Maintainer` laisse `pm-mr merge` (karl manager) fonctionner ; `push=personne`
  sur prod force la promotion **par MR**. À (ré)appliquer sur chaque repo PM-piloté.
- **Outil canonique : `pm-mr`** (RM1871) — `pm-mr create <RMid>` (push + MR + CF) /
  `pm-mr merge <iid>` (merge, conserve la branche) / `pm-mr get <iid>`. Il encapsule
  les gotchas ci-dessous (ID numérique, en-tête, re-GET de confirmation). À préférer
  au `glab` brut. `pm-branch-start` (crée la branche) + `pm-mr` couvrent le cycle git.
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
  - **En-tête d'auth** : un **PAT** passe en `PRIVATE-TOKEN: <pat>` ; un token OAuth
    `glab` en `Authorization: Bearer …` (sinon non-authentifié → 404 sur repo
    `internal`).
  - **Corps vide sur succès** possible → **re-GET** pour confirmer l'état.
  - **Conserver la branche** au merge : `should_remove_source_branch=false`.

  ```bash
  # ID numérique (pas de %2F), puis create (branche conservée) puis merge :
  glab api --hostname gitlab.iprospective.fr "projects?search=<nom-repo>"
  glab api --hostname gitlab.iprospective.fr --method POST "projects/<id>/merge_requests" \
    -f source_branch="<RM-id>-<slug>" -f target_branch="dev" -f title="…" \
    -f remove_source_branch=false
  glab api --hostname gitlab.iprospective.fr --method PUT "projects/<id>/merge_requests/<iid>/merge" \
    -f should_remove_source_branch=false
  ```
- **Tracer dans le ticket** : une fois la MR créée, renseigner le CF Redmine
  `GIT PR` (id 4) avec son URL (`pm-mr create` le fait).

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

