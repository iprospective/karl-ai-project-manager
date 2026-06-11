> 📂 **Module `git-mep` — quand lire ceci :** je code un ticket (branche) · push / MR · projet versionné · commit+push · cycle dev→test→MEP.
> **Outils :** `glab`, `mmi-pm-git-*`⚠ · **Préchargé par :** worker-dev, worker-db, worker-infra.

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
  prod_branch: master       # branche déployée en prod (master historique ; main = cible de migration)
  integration_branch: dev   # branche d'intégration : agrège les devs testés, déployée en staging (alias preprod)
```

- `prod_branch` : souvent `master` (historique), migration progressive vers `main`.
- `integration_branch` (`dev`) : agrège les branches de ticket déjà testées, avant MEP.
- **Source unique** des branches de workflow : les `environments[].branch` doivent y
  être cohérents (`staging.branch == integration_branch`, `prod.branch == prod_branch`).
- À distinguer du bloc `git:` du **frontmatter de tâche** (`git.branch`, `git.mr_url`),
  qui pointe la branche de *travail courante du ticket*, pas les branches de référence.

### Modèle d'environnements

Un projet a typiquement :
- **1 prod** (`prod`) — déployée depuis `prod_branch`.
- **1 staging** (`staging`, alias `preprod`) — déployée depuis `integration_branch` ;
  tests de non-régression avant MEP.
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
   `GIT Branche`.
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

### Workflow de mise en production (MEP) — **provisoire, évoluera**

La MEP opère sur la **branche d'intégration entière** (`integration_branch`), pas
ticket par ticket : plusieurs tickets en `a_mep` montent ensemble.

1. Déployer `integration_branch` dans l'env **preprod** ⇒ les tickets concernés passent
   `en_mep`.
2. Tests de **non-régression** sur preprod.
3. Vérification par un **testeur humain**.
4. Si OK ⇒ merge `integration_branch` → `prod_branch` + `pull prod_branch` en prod ⇒
   tickets `ferme` (`close_reason: resolu`).
   - Régression détectée ⇒ `a_corriger` (note obligatoire).

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

> Ce workflow MEP est une **v1 explicitement provisoire** (déploiement par pull
> manuel). Il sera remplacé par un mécanisme outillé (CI/CD, rollback) documenté dans
> `project/deployment.md` (template bootstrap `005-deployment`).

---

#### Commit + push systématique (obligatoire)

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

#### Remote canonique GitLab, MR, et gotchas API — v1.20.4

- **GitLab est le remote canonique** : quand un repo de code a un remote GitLab
  (typiquement `origin`, alias SSH `git:` → `gitlab.iprospective.fr`), c'est lui
  qu'on utilise **par défaut** pour push, branches et MR. C'est aussi lui que
  traque la branche d'intégration locale.
- **Miroir gogs déprécié** : le miroir `gogs:` est **déprécié de manière
  générale**. Il reste actif **uniquement sur le projet `pisceen/prestashop`**.
  Partout ailleurs, ne plus pousser vers gogs (ni le maintenir en sync) — tout
  passe par GitLab.
- **Livraison par MR** (pas de merge direct sur la branche d'intégration) : créer
  une merge request de la branche de ticket vers la branche de base (version
  active ou `dev`, cf. sous-sections suivantes), puis la merger.
- **Gotcha glab/API GitLab — les `%2F` ne passent pas** : sur
  `gitlab.iprospective.fr`, le front Apache **rejette les chemins projet
  URL-encodés** (`iprospective%2Fdolibarr%2F…` → 404 Apache). Workaround
  systématique : utiliser l'**ID numérique** du projet, récupéré sans slash via
  une recherche :

  ```bash
  # 1) trouver l'ID numérique (pas de %2F dans une recherche)
  glab api --hostname gitlab.iprospective.fr "projects?search=<nom-repo>"
  # 2) agir avec l'ID (ex. créer une MR vers la branche de version active)
  glab api --hostname gitlab.iprospective.fr --method POST "projects/<id>/merge_requests" \
    -f source_branch="<RM-id>-<slug>" -f target_branch="19.0-mmi" -f title="…" \
    -f remove_source_branch=true
  # 3) merger
  glab api --hostname gitlab.iprospective.fr --method PUT "projects/<id>/merge_requests/<iid>/merge"
  ```
- **Tracer dans le ticket** : une fois la MR créée, renseigner le CF Redmine
  `GIT PR` (id 4) avec son URL (cf. sous-section suivante).

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
- À la livraison, merge dans la branche d'intégration (via MR si le repo l'exige).
- (Multi-serveur V2) le schéma `agent/{server}/RM{id}-titre` reste l'exception
  réservée à l'orchestration distribuée ; en mono-machine, utiliser la forme
  courte ci-dessus.

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

