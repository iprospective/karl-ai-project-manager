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

1. **MR `dev → preprod`** ⇒ déployer `preprod_branch` en preprod ⇒ tickets **`a_tester_preprod`**.
2. Tests de **non-régression** sur preprod + vérification par un **testeur humain**.
3. Si OK ⇒ tickets **`a_mep_prod`** (« préprod OK, à mettre en prod » — file de MEP prod).
4. **MR `preprod → prod_branch`** + `pull prod_branch` en prod ⇒ tickets **`en_mep`**
   (déployé en prod, dernière vérification avant fermeture), puis `ferme`
   (`close_reason: resolu`).
   - Régression preprod ⇒ `a_corriger` (note obligatoire).

> ⚠ **`en_mep` = déployé en PROD**, depuis RM2893 — pas « en préprod ». Le statut dit *où
> est le code*. La recette préprod, c'est `a_tester_preprod` ; la file d'attente de la MEP
> prod, c'est `a_mep_prod`. Détail et machine d'états : `status-workflow` § Refonte RM2893.

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


## Audit hebdomadaire des environnements — mode d'emploi (RM3163)

**Pourquoi.** Le 2026-09-14, sur calyclay/calymix, sept commits poussés sur la branche RM2264
**après** le merge de sa MR, et un document de RM1937 (juillet), n'avaient jamais atteint `master`.
Personne ne l'a vu pendant un mois : les branches suivantes sont parties sans, une correction
validée par le demandeur est « revenue », et des documents périmés ont dû être repris à la main,
puis rendus cohérents avec ce qui avait été écrit entre-temps. Le teardown par ticket et le GC
sont événementiels ; rien ne faisait de point d'ensemble. **Décision Mathieu : un audit
hebdomadaire, outillé, avec historique des contrôles.**

**La règle.**
- **Chaque semaine** (début de semaine), et **à la reprise d'un projet resté > 7 jours sans
  session**, lancer `pm-env-audit --fetch` sur **l'ensemble des workspaces** (`--workspace
  client/projet` pour un seul). `pm-env-audit --last` répond « de quand date le dernier ? » :
  au-delà de 7 jours, on relance avant de reprendre du code.
- `pm-doctor` **lit** cette consignation à chaque exécution (sans relancer l'audit lui-même) et
  alerte : audit absent ou > 7 jours → avertissement, anomalie ÉLEVÉE encore ouverte → erreur.
  C'est le point d'entrée quotidien ; l'audit reste le tour hebdomadaire.
- L'audit **se consigne dans chaque projet**, dans son dépôt de données (`<workspace>/.mmi-pm/
  env-audit/`, commit + push direct — un core n'a pas de MR) : `history.md` = une ligne par
  contrôle (date, fetch, anomalies par gravité, Δ nouvelles / résolues) ; `YYYY-MM-DD_HHMM.md` =
  le détail et le diff depuis le contrôle précédent, écrit **seulement** s'il y a une anomalie ou
  un changement. C'est l'historique des checks, la preuve qu'il a eu lieu, lisible depuis le
  projet (`pm-env-audit --last --workspace client/projet`). Le repo PM ne garde qu'une synthèse
  globale locale (`var/env-audit/history.jsonl`, `pm-env-audit --last`). Les dépôts de CODE ne
  sont jamais modifiés (lecture seule ; `--fetch` ne touche que `origin/*`).
- Ce qu'il signale : **BRANCHE** (commits absents *par contenu* de l'intégration — `git cherry`,
  un cherry-pick compte comme intégré), gravité d'après **l'état réel de la MR** (API de la forge,
  `git.mr_urls` du ticket) : MR **mergée** et commits postérieurs → ÉLEVÉE (le cas RM2264, daté du
  merge), MR ouverte → info, MR fermée sans merge → moyenne ; sans MR : ticket fermé / en MEP →
  ÉLEVÉE, sinon moyenne (forge injoignable ou `--no-forge` → ce repli) ; **SALE** (fichiers non
  commités, âge du plus ancien, alerte > 7 j) ; **RETARD** (intégration locale derrière le
  remote) ; **STASH** oubliés ; **FERMÉ** (worktree de ticket fermé → obsolète, propre et
  intégré, ou à traiter — modifs non commitées ou commits non intégrés) ; **REMOTE** (fetch
  impossible).
- **Branche d'intégration retenue** : la branche par défaut du remote (`refs/remotes/origin/HEAD`,
  résolue en premier), puis `dev`, `develop`, `main`, `master` — la première qui existe. Sur un
  dépôt où `origin/HEAD` pointe ailleurs que ces noms usuels (mirroring, migration en cours), c'est
  elle qui prime : ne pas s'étonner qu'un `dev` historique mais mort ne soit pas la référence.
- **Portée par défaut** : seules les branches de **tickets** (`<RMid>-…`) et les branches
  **locales** (`refs/heads/*`, quel que soit leur nom — ce sont des worktrees actifs ou des
  branches maintenues à la main) sont examinées **par contenu**. Les autres branches **distantes**
  hors convention (miroirs amont, branches de version type `19.0-mmi`, releases…) sont **comptées**
  dans un résumé (`N branche(s) distante(s) hors convention non examinée(s)`) mais pas parcourues,
  pour ne pas payer le coût d'un `git cherry` sur des lignées entières sans rapport avec un ticket.
  `--all-branches` force l'examen par contenu de toutes les branches distantes, y compris celles-là
  — utile ponctuellement, coûteux sur un gros dépôt (voir Performance ci-dessous).
- **Traitement** : une anomalie ÉLEVÉE se traite **avant** de reprendre le projet — ouvrir la MR
  manquante, reprendre les commits (cherry-pick sur la branche courante, en **relisant** ce que
  d'autres ont écrit depuis : le contenu ancien peut contredire le CDC à jour), ou retirer ce qui
  est obsolète ; on note ce qu'on a fait dans le ticket concerné. Une anomalie moyenne se
  traite dans la semaine ; une info se lit.
- **Envs obsolètes** (ticket fermé, worktree propre, contenu intégré) : `pm-env-gc --workspace
  <ws>` pour un projet, ou `pm-env-gc --all` pour tout le parc — toujours en dry-run d'abord, puis
  `--apply` pour nettoyer réellement.
- **Corollaire du tripwire #3** : un commit poussé sur une branche de ticket **après** le merge
  de sa MR est orphelin tant qu'une nouvelle MR ne le porte pas → MR dans la foulée, ou pas de
  push. L'audit est le filet, pas la règle.

**Options utiles.**
- `--no-forge` : ne pas interroger l'API de la forge (réseau coupé, token absent, ou juste pour
  aller plus vite) — la gravité des BRANCHE retombe sur le statut du ticket seul.
- `--all-branches` : voir ci-dessus (Portée par défaut).
- `--no-consign` : ne rien écrire ni committer dans les projets — un essai, pour voir ce que
  l'audit relèverait sans laisser de trace.
- `--no-commit` : consigner (écrire `history.md` et le détail) sans committer/pousser — utile en
  debug d'un projet précis.
- `PM_ENV_AUDIT_TRACE=1` (variable d'environnement) : affiche sur stderr chaque commande git qui a
  pris plus d'1 seconde, avec sa durée — le premier réflexe pour profiler un audit lent sur un
  dépôt particulier avant de conclure à un bug.


## Licence — posée à la naissance (RM3030)

Un dépôt sans `LICENSE` n'est pas open source : personne n'a le droit de l'utiliser ni de le
modifier. La licence du code se décide **à la création du projet**, pas « plus tard » :

- `pm-project-new --license <SPDX>` (sinon la question en terminal — MPL-2.0 pour un cœur
  ouvert à modules libres ou fermés, Apache-2.0, MIT, LGPL-3.0, GPL-3.0, AGPL-3.0,
  `proprietary` ; défaut **GPL-3.0**, décision iProspective RM3029 ; hors terminal :
  `proprietary`, rien n'est publié) → consignée dans `.mmi-pm/meta.yml` (`license:`) ;
- `pm-repo-new --push-from <dépôt>` écrit et committe `LICENSE` (texte SPDX intégral,
  `templates/licenses/`, `NOTICE` pour Apache-2.0) si le dépôt n'en a pas, en reprenant la
  licence du projet PM qui le contient (`--license` pour la forcer, `--copyright` pour le
  titulaire — défaut `PM_LICENSE_HOLDER` ou iProspective).

## GitHub — créer et pousser (RM3016)

Le registre `providers` déclare GitHub (`github-public`, alias SSH `github:`) et `pm_forge`
sait y ouvrir des PR. Pour **créer** un dépôt et y pousser des branches choisies :

    pm-repo-new --forge github --path iprospective/atombox --description "…" \
                --push-from repos/atombox-webmail.git --branches main,dev --remote github

- l'owner (`iprospective`) est résolu par lecture — organisation ou utilisateur, jamais deviné ;
- un dépôt existant est refusé ; création **privée** par défaut ; branche par défaut fixée après le
  push (GitHub prend sinon la première branche reçue) ; protection de `main` si le plan le permet,
  avertissement sinon (les dépôts privés d'un plan gratuit n'en ont pas) ;
- `--remote github` pose le remote sous ce nom : `origin` (GitLab) reste intact ;
- le jeton est **par organisation** : `GITHUB__<OWNER>__TOKEN` (ex. `GITHUB__IPROSPECTIVE__TOKEN`) dans le
  **`.env` utilisateur** (`~/.config/mmi-pm/.env`), sinon `GITHUB__<INSTANCE>__TOKEN`, sinon `GITHUB_TOKEN` ; et
  `deploy/karl-agent/git-credential-pm-github` (installé dans `~/.local/bin`) le sert à `git` ; le
  repli HTTPS+jeton de l'alias canonique est `url.https://github.com/.insteadOf github:` en
  config globale — le remote stocké reste `github:owner/repo.git` (RM2328).

#### Actions au déploiement = la procédure de MEP du ticket — v2.10.0 (RM2563)

Le § *Workflow de développement* ci-dessus décrit la MEP **générique** : MR vers
`integration_branch`, puis `preprod`, puis `prod_branch`. Ce qu'il ne peut pas dire,
c'est ce que **ce ticket-là** exige en propre — migration à jouer et dans quel ordre,
constante à créer avant le premier passage, cron à (ré)installer, service à recharger,
dépôt A à déployer avant le dépôt B, jeu de données à recalculer après coup.

`deploy_actions` **est cette procédure** : la suite **ordonnée** d'étapes que suit la
personne qui met en production. Pas un pense-bête d'extras — un **runbook**. L'ordre de
la liste **est** l'ordre d'exécution.

**Où ça vit.** Champ canonique : le CF Redmine **8 « Actions au déploiement »** ; miroir
local dans le frontmatter `deploy_actions` (liste, une étape par ligne). Outil :
**`pm-task-deploy`** (`--add` / `--set` / `--clear`, et `--pull` quand la saisie a été
faite directement dans l'UI web). Le passage en `a_mep` **affiche la procédure** à qui
déploie : une procédure que personne ne relit au bon moment ne sert à rien.

**Rédaction au fil de l'eau, pas à la livraison.** C'est au moment où on écrit la
migration qu'on sait qu'il faudra la jouer — pas trois semaines plus tard devant la
prod. Une étape ajoutée après coup est une étape déjà à moitié oubliée.

**Ce qu'on y met, et ce qu'on n'y met pas.**

| | |
|---|---|
| **Oui** | les étapes **propres à ce ticket**, dans l'ordre ; la **cible** de chacune quand elle n'est pas évidente (quel env, quel dépôt, quelle machine) ; le **point de non-retour** s'il y en a un ; le **rollback** de ce ticket s'il ne se réduit pas à revenir au commit précédent. |
| **Non** | ce qui est **systématique pour l'environnement** — c'est `environments[].post_deploy` (§ *Modèle d'environnements*), déclaré une fois par env, pas recopié dans chaque ticket ; ce qui est **générique au workflow** (créer la MR, merger, `git pull`), déjà normé ci-dessus. |

Un ticket qui n'exige rien de particulier laisse la liste **vide** — c'est une réponse,
pas un oubli. Le remplissage de complaisance (« déployer le code ») coûte la crédibilité
du champ : le jour où il contient vraiment quelque chose, plus personne ne le lit.

**Sécurité prod.** La procédure ne dispense d'aucune garde : chaque commande qui modifie
la prod exige le **consentement humain explicite pour cette action précise** (tripwire
*Sécurité prod*), et le **point de restauration préalable** (snapshot ZFS du conteneur
depuis l'hôte, sur infra opensvc/LXC/ZFS) reste dû — son nom se logue avec la procédure
de rollback. Écrire la procédure ne l'autorise pas à s'exécuter : comme
`environments[].post_deploy`, `deploy_actions` est **déclaratif, jamais auto-exécuté**.

**Synchronisation.** PM → Redmine à chaque écriture (`pm-task-deploy` pousse le CF).
Redmine → PM automatiquement à chaque `pm-task-sync`, pour rattraper une saisie faite
dans l'UI web. Un CF **vide** ne remet **jamais** le miroir local à zéro : « vide côté
Redmine » veut dire « pas d'information », pas « efface ». Le vidage volontaire passe par
`pm-task-deploy --clear`, qui écrit les deux côtés.

> Le champ `deploy_actions` et le CF 8 coexistaient depuis l'origine **sans être reliés**
> — le champ n'était qu'initialisé à `[]`, jamais lu ni poussé. RM2563 ferme le circuit ;
> avant lui, ce qui y était écrit ne ressortait nulle part. **L'existant a été repris**
> (21 procédures remontées vers le CF 8), via `pm-cf-mirror-backfill` — dry-run par
> défaut, ne remplace jamais du contenu par du vide, et **signale les désaccords au lieu
> de trancher**.

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
