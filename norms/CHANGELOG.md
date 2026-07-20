# Changelog des normes

Toutes les évolutions notables sont documentées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/)

---

## [1.58.1] - 2026-07-20

### Clarifié — transport git = SSH + alias en premier choix partout (RM2328)

`git-mep` § *Remote canonique* : le push/fetch des repos PM passe par l'**alias
SSH** (`gitlab:`), forme canonique et préférée ; **HTTPS + token = simple repli**.
Explicité que l'auth repose sur la **clé GitLab dédiée sans passphrase** de `karl-dev`
(`id_ed25519_gitlab`, **RM2158**), toujours disponible sans ssh-agent — on ne convertit
pas les remotes en HTTPS. Panne silencieuse pointée : auth SSH cassée → push différé
**et** `git fetch` menteur (refs périmées → anti-collision faussée), d'où le watchdog
cockpit **RM2376**. Distinction posée : **transport (SSH)** vs **API GitLab (PAT,
HTTPS)** via `pm-mr`.

---

## [1.58.0] - 2026-07-19

### Ajouté / corrigé — layout canonique de workspace (RM2348)

`structure-reference` ne documentait que l'**ancien** modèle : `.mmi-pm` symlink
*entrant* vers un repo central `projects_root` qui **contenait** les données PM. La
réalité a évolué en sens inverse et n'était écrite nulle part — surfacé en
diagnostiquant un bug de `pm-branch-start` (branche créée dans le core PM au lieu du
repo de code).

Documenté :
- **Anatomie d'un projet** : un projet = un dossier `.mmi-pm` porté par le **core**
  (dépôt à la racine du workspace, ne révisionne que `.mmi-pm/`) ; autour, `repos/`
  (dépôts de code bare) et `envs/` (worktrees tirés de `repos/`).
- **Deux dépôts, deux destinations de commit** : le code se commite dans un worktree
  `envs/` (→ remote du code) ; la structure/projet (tout `.mmi-pm/`) dans le core
  (→ remote `-core`). Corollaire : un repo porteur de `.mmi-pm` est un core, jamais une
  cible de branche de code (invariant pour l'outillage).
- **`projects_root` = index** : le lien est **inversé**, `projects_root/…/<P>` est un
  symlink *sortant* vers le `.mmi-pm` du core (maintenu par `mmi-pm index rebuild`),
  plus l'emplacement de stockage. Ancienne section symlink marquée legacy.
- Analogue entité : `.mmi-pm-client` (core client).

## [1.57.0] - 2026-07-18

### Ajouté — réouverture d'un ticket fermé (RM2285)

Le workflow n'offrait AUCUNE transition depuis `ferme` (constat RM2140 : ticket
validé-clos impossible à reprendre proprement). Nouvelle transition
`ferme → a_faire` (module status-workflow, § Transitions valides) : note motivée
obligatoire, `close_reason` purgé, `status_history` conserve le cycle précédent.
Outillage : `pm-task-status-update` (garde-fous cible/note) + bouton « Rouvrir »
au cockpit. Nouveau périmètre sur le même sujet → préférer un nouveau ticket lié.

---

## [1.56.0] - 2026-07-15

### Ajouté — format des livrables : portable et versionné (RM2301)

NORMS ne disait nulle part sous quelle **forme** un livrable documentaire doit
exister. Un agent pouvait donc produire un audit/CDC dans un format lié à son
fournisseur de LLM (Artifact, canvas, doc hébergé) — illisible et non reprenable
par un autre agent, et hors git donc sans diff, sans revue, sans historique. Cas
réel : audit ORM de Worm (RM1981), livrable proposé en Artifact, refusé par le
demandeur ; la règle avait alors été notée dans la mémoire privée de l'agent —
soit une règle transverse appliquée par un seul agent sur un seul projet, exactement
le drift que NORMS existe pour empêcher.

Livré : nouvelle section « Format du livrable — portable et versionné » dans
`redmine-sync` (le module qui porte déjà « source canonique → miroir généré » et
le bullet Docs/Wiki). Tout livrable documentaire est du **markdown dans le repo
git** ; les rendus hébergés (Wiki via `pm-wiki-sync`) restent des miroirs générés ;
les outils de rendu vendor sont une vue jetable, jamais une source. Critère de
décision : « un autre LLM, demain, sans mon outillage, peut-il lire, éditer et
versionner ce livrable ? ». Déclencheur ajouté à la table du KERNEL.

## [1.55.0] - 2026-07-12

### Ajouté — garde-fous « bon worktree » (RM2240)

En multi-tickets parallèle (`pm-branch-start --worktree`), l'agent éditait
régulièrement dans le mauvais worktree (le `cd` n'est jamais forcé). Livré :
`pm-branch-start` termine par la ligne `→ cd <worktree>` (+ `--print-cd` =
chemin nu pour `cd "$(…)"`) ; nouveau `pm-task-cd.py` (résout `git.worktree`
du frontmatter) ; hook **pre-commit** (pm-pre-commit, posé par
pm-hooks-install) qui REFUSE un commit de ticket hors de son worktree
enregistré, refuse une branche `<id>-…` sans ticket local (tripwire #13, avant
même le push) et avertit sur un commit d'intégration quand la session a des
worktrees de ticket actifs ; règle worker-common « se placer dans le bon
worktree » + ligne de couverture session-tooling.

---

## [1.54.0] - 2026-07-12

### Ajouté — session-tooling : sous-section « Idiomes fréquents » (RM1996)

Le module `session-tooling` listait les outils canoniques mais pas leurs idiomes
d'usage, forçant les agents à relancer `--help` à chaque session. Ajout des
idiomes constatés en séance : contenu long via stdin (`--note -`,
`--description -`/`--description-file`, `--set-from-file` — évite aussi la
protection Bash « newline + `#` »), `--list-next` (transitions valides),
auto-assignation (`en_cours` ⇒ `--assign-to me` implicite), `--project` explicite
quand la détection cwd échoue, `--dry-run`, et `PM_CORE_DIR=` pour un script
lancé depuis un worktree sans `.env`.

---

## [1.53.0] - 2026-07-11

### Modifié — tripwire #13 étendu : AUCUN identifiant séquentiel prédit (RM2232)

Après un 4e incident (merge de la MR !122 d'une autre session sur iid prédit),
le tripwire #13 s'étend de « RM-id » à **tout identifiant séquentiel partagé**
(RM-id, iid de MR GitLab…). Décision explicite Mathieu : la prédiction est
**interdite** ; tout numéro se capture de la sortie d'un script. Outillage :
`pm-mr create --porcelain` (iid nu) / `--merge` (create+merge atomique, l'iid
ne transite pas par l'appelant) / `pm-mr merge --expect-rm <id>` (refuse une MR
dont la branche source ne porte pas l'id attendu).

---

## [1.52.0] - 2026-07-09

### Ajouté — tripwire #13 « jamais de RM-id prédit » + `pm-task-add --porcelain` (RM2170)

La séquence des ids Redmine est **globale à l'instance** ; avec plusieurs agents/projets
en concurrence, le prochain id n'est pas prévisible. Deux incidents (RM2142, RM2163 :
prise/branche/statut posés sur le mauvais ticket) ont montré le risque de « dernier id
vu + 1 ».

- **KERNEL** : nouveau tripwire **#13** — ne jamais saisir un RM-id de mémoire ; toujours
  le **capturer** de la sortie de l'outil, et **consommer la variable** dans les commandes
  enchaînées (jamais un littéral).
- **`session-tooling`** : section « Capture d'un RM-id fraîchement créé » (recette
  `ID=$(pm-task-add … --porcelain)` + chaînage status-update/branch-start/task-link).
- **Outillage** : `pm-task-add.py` gagne **`--porcelain`** (alias `--id-only`) — n'imprime
  que l'**id nu sur stdout**, tous les logs sur stderr ; l'id est émis dès que le ticket
  existe côté Redmine (robuste à un échec de post-traitement). Documenté dans le skill
  `mmi-pm-task-add`.

---

## [1.51.0] - 2026-06-23

### Modifié — frontière `docs/` : aspects libres hors `project/` (RM2043, privsep)

Étape 0 du volet privsep PM. Les **aspects-docs libres** d'un projet (roadmap,
data-model, orchestrator, specs…) quittent `project/` pour **`.mmi-pm/docs/`**
(group-writable `mathieu`, wiki-syncés) ; `project/` ne garde que les **canoniques**
`overview.md` + `environments.md` (couche `mathieu-pm`, mutation via `mmi-pm`, hors
wiki-sync). Le discriminant reste *« a un filet de réconciliation (wiki-sync 3-way),
ou pas »*.

- **`structure-reference`** : nouveau pattern `docs_dir = {project}/docs` ; arbo et
  table des chemins mises à jour ; symlink de confort `<workspace>/docs → .mmi-pm/docs`.
- **`project-modeling`** : section « Aspects » scindée canoniques (`project/`) vs
  libres (`docs/`) ; la cascade de contexte lit désormais `project/` **et** `docs/`.
- **KERNEL** : cascade projet = `{project_dir}/*.md + {docs_dir}/*.md + {project_memory_dir}/*.md`.

Outillage rendu *docs-aware* (mêmes commits) : `pm.config.yml`/`pm_paths` (`docs_dir`),
`pm-wiki-sync` (scrute `docs/` seul ; `environments` sort du wiki-sync), `pm-context-budget`
(cascade `docs/*.md`), `karl-agent._project_docs` (surface `project/`+`docs/`), `pm-doctor`
(invariant : aucun aspect libre résiduel dans `project/`), `pm-project-new` (scaffold `docs/`
+ symlink). Migration réelle des données = `pm-docs-migrate --all` (outil idempotent /
dry-run / réversible), exécutée séparément sur le repo `ai-projects`.

## [1.50.0] - 2026-06-19

### Précisé — `pm-task-tick` : garde « ticket fermé » (RM2053)

Module `roi-pricing` : documentation du garde qui empêche d'attribuer une tick à un
ticket `status: ferme`. Le résolveur retient le signal le plus fort **parmi les tickets
ouverts** ; un tour ne touchant que du fermé ne ticke rien ; un sentinel `CURRENT_TASK`
pointant un ticket clos est ignoré ; fail-safe statut illisible → ouvert. Évite que la
cérémonie de clôture / le suivi post-fermeture ne gonfle un ticket déjà fermé.

## [1.49.0] - 2026-06-19

### Ajouté — `pm-protect` : enforcement GitLab des branches protégées (RM2052)

Outil **`pm-protect`** (`--repo` / `--project-id`, `--dry-run`) appliquant la
**politique de protection standard** d'un projet PM (idempotent, `allow_force_push=
false`, token *manager*), enforcement concret du tripwire #3 :

| Branche | push | merge |
|---|---|---|
| prod (`main`/`master`) | personne | Maintainer |
| intégration (`dev`) | Maintainer | Maintainer |
| `preprod` (si présente) | personne | Maintainer |

`git-mep` documente la table comme standard. `merge=Maintainer` laisse `pm-mr merge`
fonctionner ; `push=personne` sur prod force la promotion par MR.

## [1.48.0] - 2026-06-19

### Renforcé — Pas de commit direct sur une branche protégée (RM2051)

Tripwire #3 (*Branche par ticket + livraison par MR*) étendu : **aucun commit/push
direct sur une branche protégée**, intégration (`dev`) **ET** prod (`main`/`master`),
**dès le flux 2 branches** (pas seulement le flux 3 branches opt-in). La promotion
`dev`→prod passe elle-même par une MR. Motivation : des commits directs sur `main`
(RM2035/2038/2048) provoquaient divergences et **collisions de version NORMS**.
Enforcement GitLab : protéger `dev` et le `prod_branch` (push direct interdit, merge
de MR seul). Détail dans `git-mep`.

### Documenté — Split clone-dev / runtime pour les secrets (`PM_CORE_DIR`)

`PMConfig` charge le `.env` de `pm_dir` s'il existe (runtime canonique), **sinon** le
`.env` du core pointé par **`PM_CORE_DIR`** ; à défaut, **erreur explicite** (au lieu
d'un `roots.projects_root non défini` obscur) expliquant que le clone de dev ne porte
pas les secrets. `git-mep` + `.env.example` mis à jour.

## [1.47.0] - 2026-06-19

### Ajouté — Rotation des tokens GitLab à J-7 + vérif début de session (RM2046)

Politique de rotation des PAT GitLab de karl **clarifiée et outillée** : rotation
**une semaine avant péremption** (seuil J-7), pour **tous** les `GITLAB_*_TOKEN`
(manager, worker, futurs), pas seulement le manager.

- Nouvel outil **`pm-token-check`** : rapporte `expires_at`/J-N de chaque token via
  `GET /personal_access_tokens/self` (valeur jamais imprimée). Code retour `2` si au
  moins un token est sous le seuil (cron/hook-able), `0` sinon. `--rotate-due` rote
  (`…/self/rotate`) les tokens dus et **réécrit le `.env` canonique atomiquement**
  (tripwire #11 ; ancienne valeur révoquée aussitôt). Options `--threshold`,
  `--rotate-expiry-days` (défaut 365), `--dry-run`.
- **Déclencheur KERNEL** ajouté : « début de session PM / périodiquement → péremption
  des PAT GitLab → `pm-token-check` ».
- Section *Rotation des tokens* de `git-mep` réécrite (remplace l'ancienne cadence
  floue « ~hebdo sur ~1 mois ») ; `.env.example` mis à jour.

## [1.46.0] - 2026-06-19

### Précisé — Fermeture bloquée par une sous-tâche ouverte (piège diagnostique)

La précondition « un parent ne se ferme que si toutes ses sous-tâches sont fermées »
(déjà énoncée dans `modules/status-workflow.md`) est désormais **remontée en tripwire**
(KERNEL #4, *Sync statut MD↔Redmine*) et complétée du **symptôme diagnostique** :

- Le refus Redmine est **silencieux** (PUT 204, `status_id` ignoré, statut inchangé) et
  les scripts l'**interprétaient à tort** en « permission *Edit issues* manquante ».
- Ce n'est lié **ni au rôle ni au tracker** (« Evolution » = « Tâche », mêmes droits).
- Diagnostic autoritatif : `GET /issues/<id>.json?include=allowed_statuses` puis
  `?include=children` (un enfant non clos = le blocage).

Côté outillage : `pm-task-status-update` diagnostique désormais lui-même, sur échec de
transition vers `ferme`, les **sous-tâches ouvertes** et les annonce, au lieu de
supposer un manque de droits.

## [1.45.0] - 2026-06-16

### Ajouté — Module `redmine-sync` : principe de parité Redmine ↔ PM

Nouveau **module à la demande** `modules/redmine-sync.md` (groupe « workflow &
Redmine ») portant le **principe de parité** : **on cherche en permanence à établir
(ou rapprocher) la synchronisation entre les données Redmine et les données PM**,
pour qu'humains et agents IA voient toujours le même état. Redmine = vitrine humaine,
fichiers MD = plan de travail des agents, mais **même état** sous deux angles.

- Placé en **module** (chargé à la demande), pas dans le KERNEL : le principe est un
  objectif directeur, pas un tripwire toujours-chargé → coût de contexte runtime nul.
- **Découvrable** via une ligne de déclencheur ajoutée au KERNEL (« j'introduis/fais
  évoluer une donnée ou un artefact partagé Redmine↔PM »).
- Se pose en **ombrelle** des tripwires de sync existants (statut #4, description
  vivante #9, traçabilité #12, liens, métriques, wiki) — il les chapeaute, ne les
  duplique pas.
- Conséquence pratique inscrite : concevoir la sync **avant** la copie, depuis une
  **source canonique unique** ; à défaut de parité parfaite, réduire l'écart, jamais
  l'agrandir.
- Motivé par RM2016 (norme demande/CDC répliquée CLI + Redmine UI) et le script
  `redmine-template-sync.py` (miroir des templates d'issue depuis source unique).
- Ajouté au `manifest.yml` (assemblage).

## [1.44.0] - 2026-06-16

### Ajouté — Champ `post_deploy` à l'aspect `environments` (schema aspect 1.9.0 → 1.10.0)

Nouveau champ optionnel **par environnement** : `post_deploy`, **liste de commandes
shell** à exécuter après un déploiement sur cet env (ex. purge du cache applicatif).
Forme **scriptée** de la procédure de déploiement, à préférer à la prose (qui ne sert
plus qu'à expliquer le *pourquoi*).

- **Déclaratif, non auto-exécuté** : documente les commandes ; aucun outil ne les lance
  automatiquement. Un humain les exécute délibérément — sur la prod, consentement
  explicite requis (cf. « Règle de sécurité prod »).
- **Chemins absolus obligatoires** : `rm -rf var/cache/*` en relatif vise `/var/cache`
  (dossier système) si lancé du mauvais cwd → toujours ancrer sur `app_path`.
- Module `environments` (liste des champs) + template
  `templates/aspects/common/environments.md` mis à jour.

## [1.43.0] - 2026-06-14

### Corrigé — Membership « Agents IA » par défaut sur un nouveau projet (RM1977)

`pm-project-new.py` ajoute désormais un **3ᵉ membership par défaut** : groupe
`Agents IA` (id 73) en `Intervenant` (role 7), en plus de `Admin`/Manager et
`iProspective`/Intervenant. Sans ce groupe, un nouveau projet Redmine n'était
**pas accessible aux agents IA** (karl & co). Rôle universel sur l'instance
(`Développeur` reste ajouté ad hoc sur les projets dev). Module
`project-creation` (tableau memberships) mis à jour.

## [1.42.0] - 2026-06-13

### Ajouté — Budget de contexte par rôle (RM1943)

Mesure et garde-fou du contexte **toujours-chargé** d'une session, par rôle :

- **`scripts/pm-context-budget.py`** : compose le contexte fixe d'un rôle
  (pont AGENTS.md + CLAUDE.md PM + KERNEL + modules **préchargés** du rôle +
  worker-common + addendum) et l'estime en tokens (octets/3,6). `--all-roles`
  (tableau comparatif + Δ vs NORMS monolithique d'avant RM1922), `--role`,
  `--before`, `--entity/--project` (cascade réelle), `--check`.
- **Plafond** `pm.config.yml :: context.budget_tokens` (`default` + override
  par rôle) ; **`pm-norms-doctor` échoue** si un rôle dépasse — invariant
  anti-régression : précharger un module lourd pour un rôle est désormais
  refusé au-delà du budget.
- Mesure de référence (2026-06-13) : worker-dev **21,2k** vs **39,5k** avant
  factorisation (**−46 %**) ; reviewer/summarizer **−78 %**. Module
  `governance` § Budget de contexte + `MAINTAINING.md` §11.

## [1.41.0] - 2026-06-13

### Ajouté — Outillage NORMS livré : pm-branch-start, pm-doctor, --list-next (RM1923)

Trois trous d'outillage comblés ; les ⚠ correspondants du KERNEL sont levés :

- **`pm-branch-start.py <RMid> [--from BR] [--take]`** (remplace le placeholder
  `mmi-pm-git-*`) : crée/checkout la branche `<RMid>-<slug>`, renseigne le CF
  Redmine **GIT Branche (id 3)**, met à jour `git.repo`/`git.branch` du
  frontmatter + log, auto-commit (RM1834) ; `--take` enchaîne la prise.
  Garde-fou : refuse ai-projects comme repo cible. Module `git-mep` § Workflow.
- **`pm-doctor.py`** : valide la cohérence des paires redondantes par
  construction — `used_by_clients ↔ provided_by` et `implements ↔
  implemented_by` (RM1837) — + existence des cibles. Exit 1 si incohérence.
- **`pm-task-status-update.py --list-next`** : liste les transitions NORMS
  valides depuis le statut courant (table du module `status-workflow` encodée),
  reprise d'`en_pause` via `status_history`, et marque celles que le compte API
  peut réellement poser côté Redmine (`include=allowed_statuses`).
- `redmine.reference.yml` : CF **3 GIT Branche**, **4 GIT PR**, **14
  Environnement de test** ajoutés à la référence.
- Restent suivis par RM1923 : `pm-sync-views`, `pm-sync-links` (durée de vie
  courte : la co-location C3/RM1942 supprime les symlinks), hook post-commit
  de report (recouvre RM1895).

## [1.40.0] - 2026-06-12

### Ajouté — Auto-commit git des scripts pm-* (RM1834 piste A)

Les scripts PM committent et poussent **eux-mêmes, atomiquement**, les fichiers
qu'ils écrivent (`scripts/pm_git.py`) :

- `git commit -- <chemins explicites>` : impossible d'embarquer un fichier
  stagé par une session concurrente ; verrou local (flock) sérialise les
  invocations sur la machine ; **non-fatal** (échec ⇒ warning, l'opération
  principale aboutit ; push rejeté ⇒ commit local conservé, jamais de
  rebase/merge dans l'arbre partagé).
- Câblé dans : `pm-task-add` (+ MD parent), `pm-task-status-update`,
  `pm-task-comment`, `pm-task-link` (add/rm/parent/sync), `pm-task-sync`,
  `pm-task-report` (commit de lot en `--all`), `pm-task-metrics-push`.
- Interrupteurs `pm.config.yml :: git.autocommit` / `git.autopush` ;
  flag `--no-commit` par appel.
- Module `git-mep` : la règle manuelle « commit+push systématique » reste
  obligatoire pour les **édits libres** et le workspace de code ; pour toute
  opération passée par un script PM, plus rien à committer à la main.

## [1.39.0] - 2026-06-12

### Modifié — Outillage métriques : réconciliation RM1806/RM1819 (RM1825)

Le doublon de report des métriques temps/tokens est résolu :

- **`pm-task-metrics-push.py` = estimation seule** (`--estimate` : CF21/22/25 +
  `estimated_hours`). Les modes `--commit`/`--cumul` sont **retirés** (stubs
  d'erreur orientant vers le remplaçant). Les marqueurs frontmatter
  `metrics.reported_*` sont obsolètes (conservés, plus jamais écrits).
- **`pm-task-report.py` = report exclusif de la consommation** (time_entries
  CF16 ancrées sur les entrées datées du `.log.md`, dédup par ledger
  `reporting.time_entries[]`, resync cumul CF17 « Tokens passés »).
- Table d'outillage (module `session-tooling`) : la ligne « estimation /
  métriques / temps-tokens » est éclatée en 3 lignes (estimation / mesure /
  report conso).
- La **note Redmine par commit** (matrice du module `traceability`,
  `traceability.commit_note_level`) reste une norme **comportementale** de
  l'agent — elle n'était implémentée que par le mode `--commit` retiré ;
  aucun changement de norme, seul le support automatique disparaît.

## [1.38.0] - 2026-06-11

### Ajouté — Relation « implémentation » entre projets (§ « Relation "implémentation" entre projets »)

Nouveau type de relation **inter-projets** (RM1837), distinct du partage cross-client :
un projet peut être l'**implémentation** d'un projet **général** (interface ↔
implémentation). Le général définit procédures/templates/conventions/assets
réutilisables, l'enfant les applique à un contexte (client, instance).

- Relation **plusieurs-à-plusieurs** : champs `project/overview.md`
  **`implements: [...]`** (côté implémentation) et **`implemented_by: [...]`** (côté
  général), tous deux des **listes**, redondants par construction, cohérence validée par
  `pm doctor` (à venir).
- Distinct de `provided_by` (livrable consommé) — les deux peuvent coexister.
- Cas canoniques : **projets infra client → `iprospective/infrastructure`** (cumulatif
  avec la détection « projet infra » qui conditionne `008-infra-analysis`) ; **instances
  produit client → projet produit général**.
- Conséquences opérationnelles documentées : **placement des assets** (réutilisable →
  repo général ; spécifique → enfant), **tickets cross-projet** (besoin générique → ticket
  dans le général, relié via `relates`).
- **Pas de cascade d'aspects** (déclaratif, comme le cross-client).
- Première application : `abatik/infra implements iprospective/infrastructure` +
  backfill `calyclay/infra` (exemple vécu RM1835).
- Reste à outiller : validation `pm doctor` des paires `implements`/`implemented_by`,
  geste CLI de création de ticket cross-projet.

---

## [1.37.0] - 2026-06-09

### Ajouté — Règle de propagation « source unique → consommateurs » (§ « Synchronisation de la configuration Redmine »)

Quand un **paramètre canonique** évolue (taxonomie de `type`, mappings
`TYPE_TO_TRACKER` / `type_to_activity` / `task_type_cf`, IDs Redmine, statuts,
priorités, énumérations), **tous** les scripts/consommateurs qui le référencent
doivent être mis à jour dans le **même changement** — privilégier la lecture de la
source à l'exécution (ex. cockpit karl-agent via `pm-task-add --list-types`),
sinon resynchroniser le miroir dans le même commit. Anti-drift côté écriture.

### Corrigé — Taxonomie `type` réconciliée (les 13 valeurs créables)

`TYPE_TO_TRACKER` (gate de création de `pm-task-add`) ne couvrait que 7 types et
ignorait `audit`, `research`, `refactoring`, `security`, `performance`, `design`
— pourtant cartographiés dans NORMS (routage worker) et `type_to_activity`.
Désormais les **13 types canoniques** sont créables (trackers dédiés pour
`bugfix`/`feature`/`assistance`, le reste → « Tâche »). `pm-task-add --list-types`
expose la liste (source de vérité machine) ; `redmine.reference.yml ::
type_to_activity` complété pour les nouveaux types ; le cockpit karl-agent peuple
son sélecteur dynamiquement.

---

## [1.36.0] - 2026-06-09

### Modifié — Fusion `staging` / `preprod` (§ « Environnements », § « target_env », § « Modèle d'environnements »)

`staging` et `preprod` désignaient le même environnement (non-régression déployé depuis
`integration_branch` avant MEP). Ils sont désormais **fusionnés en un seul env** :
**valeur canonique `staging`**, `preprod` conservé comme **alias accepté**. Retiré
`preprod` de l'énumération standard des noms d'env (`environments[].name`) et de
l'énum `target_env`. Le narratif du workflow MEP et le libellé du statut Redmine id 20
(« MEP/Tester en preprod ») restent inchangés — `preprod` y reste un alias valide de
`staging`. Templates mis à jour : `aspects/common/environments.md`, `task.md`,
`bootstrap-tasks/003-environnements.md`.

---

## [1.35.0] - 2026-06-08

### Ajouté — Outillage obligatoire en session PM (§ « Outillage obligatoire en session PM »)

Principe : en session PM, toute opération touchant à l'**état des tâches, branches git,
repos/submodules ou tickets Redmine** passe par les skills/scripts PM dédiés, jamais à la
main. **Règle anti-trou** : une opération sans outil est un trou à combler (créer le
script), pas une exception manuelle. Les opérations amendant l'état d'une tâche sont
branchées derrière `pm-task-status-update.py` (source unique), qui propage Redmine + MD +
log + worklog de session ; ce dernier est alimenté automatiquement via `pm_session_hook.py`
(RM1875). Table de couverture actuelle incluse — **trou identifié : branches / repos /
submodules** (obligations existantes sans outil dédié). Audit des manques à mener.

---

## [1.34.1] - 2026-06-08

### Clarifié — Création d'un skill PM (§ « Skills PM »)

Explicitation : un skill faisant partie de l'outillage PM se crée **dans `skills/<nom>/`**
(versionné) + script dans `scripts/pm-*.py`, **jamais** dans le dossier skills perso
(`~/.claude/skills/`). Lancer `pm-skills-sync.py` pour le symlinker, l'ajouter au
`skills/README.md`. L'état instance-local d'un skill (worklogs de session, caches) reste
hors repo. Motivé par la création du skill `mmi-pm-session-status`.

---

## [1.34.0] - 2026-06-08

### Ajouté — Champs SSH d'environnement (`ssh_alias` / `ssh_target`)

L'aspect `environments.md` gagne deux champs par env (§ « Environnements ») :
`ssh_alias` (alias `~/.ssh/config`, avec `ProxyJump`/clés préconfigurés) et
`ssh_target` (cible explicite `user@hostname`). **Règle d'usage** : pour se connecter,
utiliser `ssh_alias` s'il est renseigné, sinon `ssh_target` ; `host`/`user` redeviennent
indicatifs (préfixe des logs distants, contexte). Template
`templates/aspects/common/environments.md` mis à jour (schéma aspect `1.8.0 → 1.9.0`).

## [1.33.0] - 2026-06-08

### Ajouté — Passe agent-testeur conditionnelle (`requires_agent_test`)

La passe `a_tester_dev` (test par un agent/humain ≠ le dev) n'est plus systématique : un
champ tâche `requires_agent_test` (`default`|`oui`|`non`|`demander`) la conditionne, avec
défaut projet (`defaults.requires_agent_test`) et **défaut système `non`**. Routing en fin
de dev : `oui` → `a_tester_dev` ; `non` → `a_tester_demandeur` (**nouvelle transition
`en_cours → a_tester_demandeur`**, bypass) ; `demander` → l'agent demande au demandeur.
Mappé sur le **CF Redmine 27** « AI Test par agent » (énum Oui/Non/Demander = 39/40/41 ;
vide = `default`) — `redmine.reference.yml :: agent_test_values`, `.env ::
REDMINE_CF_AGENT_TEST_ID`. `pm-task-add.py` : option `--agent-test` + champ frontmatter +
push CF si ≠ default. Workflow Redmine `En cours → À tester demandeur` activé côté instance.

## [1.32.0] - 2026-06-07

### Ajouté — Skills PM distribués cross-instance (§ Skills PM)

Nouveau dossier `skills/` à la racine du repo PM : héberge les skills Claude Code
(`SKILL.md`) transverses au PM, distribués à toutes les instances. Comme Claude Code
n'auto-découvre les skills que depuis `~/.claude/skills/`, le script
`scripts/pm-skills-sync.py` crée les symlinks nécessaires (idempotent, ne supprime jamais
un vrai dossier, `--dry-run`/`--prune`). Étape ajoutée au README (Installation). Premier
skill versionné : `mmi-env-sync` (synchro d'un environnement dev/test depuis la prod —
BDD + fichiers — avec adaptations de sécurité). Distinct des skills personnels
(`claude-skills`) et agents (`agents-skills`).

## [1.31.0] - 2026-06-04

### Documenté — Transitions Redmine « assignee-only » (§ Phase d'étude → Synchronisation)

Certaines transitions du workflow Redmine (`etude_chiffrage_a_valider` [14→21],
`a_tester_demandeur` [→9]) ne sont autorisées que si le ticket est assigné au compte API
courant. Comme elles réattribuent au demandeur dans le même PUT, le changement de statut
était refusé silencieusement (204, statut inchangé). `redmine-post-note.py` s'auto-assigne
désormais d'abord pour débloquer la transition, puis pousse statut + réattribution finale.
Mapping inverse `pm-task-sync.py` complété (id 21 → `etude_chiffrage_a_valider`). Constaté
sur RM1836.

## [1.30.1] - 2026-06-04

### Clarifié — « Ne committer que ses propres modifs » vaut dans TOUS les repos partagés

La règle de vérification active au commit (v1.29.0, § « Commit + push systématique »)
ne visait explicitement que `ai-projects`. Généralisée : elle s'applique aussi au repo
système **`project-management`** (NORMS, `templates/`, `scripts/`, `pm.*.yml`) et au
workspace de code — tous fréquemment dirty en concurrence. Ne jamais embarquer dans un
commit un fichier qu'on n'a pas soi-même modifié (ex. `pm.pricing.yml`,
`pm-task-tick.py` laissés modifiés par une autre session pendant une édition de NORMS).

## [1.30.0] - 2026-06-04

### Ajouté — Projets infra : ticket d'analyse de l'infra par défaut (template `008-infra-analysis`)

Tout projet de nature **infrastructure** (slug/nom « infra », ou aspect
`hosting`/`infrastructure` — gestion de serveurs/hyperviseurs/réseau/stockage plutôt
qu'une application unique) doit par défaut porter un **ticket d'analyse de l'infra** :
état des lieux matériel, stockage (disques + SMART, pools/RAID), charges hébergées,
monitoring, et une section **anomalies** d'où découle un ticket dédié par anomalie
significative. Le livrable est un document vivant (`docs/infrastructure.md` dans le
workspace, ou aspect `project/hosting.md`).

- Nouveau template de bootstrap **`templates/bootstrap-tasks/008-infra-analysis.md`**
  (`default_checked: true`, `applicable_when` = projet infra uniquement).
- NORMS § « Tâches de bootstrap » : ligne ajoutée au tableau des templates + encadré de
  règle « Projets infra → ticket d'analyse par défaut ».
- Première application : projet `calyclay/infra` (serveur `srve`), audit du 2026-06-04.

> Note : le CHANGELOG ne portait pas d'entrée `[1.29.0]` (bump appliqué dans
> `NORMS.md` — règle « Vérification active au commit » — sans entrée dédiée). Trou
> laissé tel quel, hors périmètre de cette mise à jour.

## [1.28.0] - 2026-06-04

### Ajouté — Statut `etude_chiffrage_a_valider` (Etude/CDC à valider, id 21) : validation de la phase d'analyse par le demandeur

La phase d'étude/qualification (v1.25.0) gagne une **étape de validation** avant le
passage au développement. L'agent ne transitionne plus directement de
`etude_chiffrage_en_cours` à `a_faire` : il soumet d'abord son livrable (CDC +
chiffrage) au demandeur.

- Nouveau statut NORMS **`etude_chiffrage_a_valider`** → Redmine **id 21**
  (« Etude/CDC à valider »).
- **Réattribution automatique au demandeur** (author ; author == karl → Manager IA)
  par `pm-task-status-update.py` — même résolveur que `a_tester_demandeur`. C'est le
  pendant amont du `a_tester_demandeur` aval.
- Nouvelles transitions : `etude_chiffrage_en_cours → etude_chiffrage_a_valider`
  (étude finie), `etude_chiffrage_a_valider → a_faire` (validé), `→ etude_chiffrage_en_cours`
  (retour demandeur), `→ ferme` (abandon).
- Sources mises à jour : `redmine.reference.yml` (`statuses.etude_chiffrage_a_valider: 21`),
  `redmine_utils.py` (fallback), `pm-task-status-update.py` (logique d'attribution +
  usage), table de mapping NORMS↔Redmine, machine d'états, enum `status`,
  skill `mmi-pm-task-status-update`.

Rétrocompatible : aucun ticket existant impacté ; le saut direct `en_cours → a_faire`
reste techniquement possible mais n'est plus le chemin nominal pour les tickets étudiés.

## [1.27.0] - 2026-06-03

### Ajouté — Statut d'entrée `nouveau` (Nouveau, id 1) + `pm-task-add --status`

Le statut Redmine natif `Nouveau` (id 1) devient un **statut NORMS de première
classe** sous le nom `nouveau`, comme **statut d'entrée** de la state-machine.

- `pm-task-add.py` crée désormais par défaut un ticket en `nouveau` (ticket déposé,
  non encore trié), avec `author_id` posé mais **sans `assigned_to`**. Le MD reflète
  `status: nouveau` (plus de divergence MD↔Redmine : avant, le MD posait `a_faire`
  alors que Redmine retombait sur `Nouveau` faute de `status_id` au POST).
- Nouveau flag **`pm-task-add.py --status <statut>`** : crée en `nouveau` puis
  transitionne vers le statut demandé via `pm-task-status-update.py` (couplage NORMS
  conservé : assignation karl pour `en_cours`, note, `status_history`).
- Sources mises à jour : `redmine.reference.yml` (`statuses.nouveau: 1`),
  `scripts/validate-task.py` (`VALID_STATUSES`), table de mapping NORMS↔Redmine.
- `redmine_utils.create_redmine_issue()` accepte un paramètre optionnel `status_id`
  (None ⇒ défaut tracker = Nouveau).

Rétrocompatible : les tickets existants en `a_faire`/`en_cours`/… restent valides.

## [1.24.0] - 2026-06-02

### Ajouté — Champ `logs.access` (aspect `environments.md`) + convention access logs prod

Ajout du champ `logs.access` à l'aspect `environments.md` (template bumpé en 1.8.0),
à côté de `logs.app` et `logs.fpm`, pour déclarer l'access log du serveur web par env.

- **Convention prod iProspective (OVH)** désormais documentée (§ Environnements) :
  les access logs nginx vivent sur le serveur hébergeur à
  `/var/log/nginx/<domaine>_access.log` (+ `<domaine>_error.log`), un fichier par vhost
  (ex: `sfy-srv1:/var/log/nginx/calicote.com_access.log`). Préfixe `<host>:` si distant.
- Cas d'usage : analyse de la charge de crawl (bots/scrapers), diagnostic de pics,
  audit des accès.
- Rétrocompatible : les instances existantes (schema 1.7.0) restent valides ; le champ
  est optionnel.

## [1.23.0] - 2026-06-02

### Modifié — Consolidation traçabilité commit/note (anti-doublon, anti-contradiction)

Factorisation des règles éparses sur « quand commiter / quand noter », qui
vivaient en 3 endroits avec des cadrages divergents (discrétionnaire vs
systématique). Source de vérité unique désormais.

- **Nouveau bloc canonique** « Unité de traçabilité : l'étape significative »
  (§ Collaboration multi-agents) : l'unité tracée est l'**étape significative**
  (pas le fichier, pas la frappe). À cette frontière → message de commit **court**
  + note Redmine **détaillée** (réf commit + temps + tokens) + entrée `.log.md`
  technique + transition de statut si livraison. Même synthèse de fond, deux
  granularités — pas de triple rédaction.
- **Matrice unique « quand poster une note »** : commit de travail/livraison/
  structurant → oui ; événement structurant **sans commit** (cahier des charges,
  réflexion) → note complémentaire ; commit trivial/housekeeping → non ; statut/
  `done_ratio` → non ; maj description → oui (renvoi § dédiée).
- **Niveau configurable** `pm.config.yml :: traceability.commit_note_level`
  (`work` défaut | `all` test | `none`) — pour calibrer le bruit à l'usage.
- L'ancien « Double traçabilité » est remplacé par ce bloc ; la § ROI
  « Journalisation par commit » ne garde que les **métriques** (time_entry + CF)
  et renvoie à la matrice canonique pour le *quand/quoi* de la note. Scope des
  métriques resserré au commit **de travail**.

## [1.22.0] - 2026-06-02

### Ajouté — Note Redmine systématique par commit

Un commit rattaché à une tâche s'accompagne désormais **toujours** d'une note
Redmine human-readable : référence du commit (SHA + URL GitLab), temps + tokens
de l'incrément, et ce qui a été livré. Comble le trou de la v1.21.0 (les commits
n'allaient que dans le `.log.md`, invisible des humains, + une time_entry peu
lisible).

- § « ROI assisté par IA » → « Journalisation par commit » : ajout du bloc
  « Note Redmine systématique par commit (obligatoire) » + clause anti-spam
  (regroupement possible de petits WIP rapprochés ; un commit de livraison/jalon
  garde sa note propre).
- § « Double traçabilité » : ajout de l'exception systématique « le commit » pour
  lever l'ambiguïté avec la règle anti-bruit (« pas chaque micro-aller-retour »).

## [1.21.0] - 2026-06-02

### Ajouté — Resync config Redmine + documentation temps/tokens dans Redmine

Nouvelle section « Synchronisation de la configuration Redmine (obligatoire,
périodique) » : les IDs Redmine (statuts, trackers, priorités, custom fields,
activités) sont propres à l'instance et mutables, et référencés en dur (`.env`,
`knowledge/redmine/api.md`, constantes scripts). Règle de revérification
périodique contre l'instance live + endpoints `GET` de référence + table des CF
dédiés actuels. Gap outillage signalé (`redmine-config-check.py` à écrire).

Dans § « ROI assisté par IA », deux sous-sections :
- « Documentation dans Redmine — champs dédiés » : estimation poussée sur CF 21
  (`Tokens prévus`), CF 22 (`Temps estimé IA (h)`), `estimated_hours` natif ;
  cumul sur CF 17 (`Tokens passés`). Estimation établie **à la création**, **à la
  prise de ticket** si manquante, et réestimée **à la mise à jour de desc** si
  conséquente.
- « Journalisation par commit — temps + tokens » : à chaque commit, report du
  delta consommé depuis le commit précédent en saisie de temps Redmine
  (`POST /time_entries.json` : `hours`, `activity_id`, CF 16 `Tokens`). Le hook
  `pm-task-tick` reste la base de mesure. Gap outillage signalé (push Redmine
  non encore implémenté).

## [1.20.3] - 2026-06-01

### Ajouté — Outillage de la hiérarchie parent/enfant

Dans § « Liens entre tâches », nouvelle sous-section « Hiérarchie parent/enfant ».
`parent_task` / `sub_tasks` sont l'**attribut natif Redmine `parent_issue_id`** (pas
une relation) : ils sont désormais entièrement outillés, plus d'édition manuelle.

- `pm-task-add --parent <RM>` : crée un ticket enfant (POST `parent_issue_id` +
  `parent_task` côté enfant + `sub_tasks` côté parent + logs).
- `pm-task-link parent <child> <parent>` / `--unset` : (re)pose, déplace ou détache le
  parent d'un ticket existant (PUT Redmine + migration des `sub_tasks` ancien→nouveau).
- `pm-task-sync <RM>` : réconcilie `parent_task` depuis `issue.parent.id` et maintient
  les `sub_tasks` locaux (réflexion read d'un changement fait côté Redmine UI).
- Cœur partagé `scripts/pm_hierarchy.py` + `redmine_utils.set_issue_parent()` /
  `create_redmine_issue(parent_issue_id=…)`.

Règles d'intégrité : parent unique, pas d'auto-parent ni de cycle, `sub_tasks` dérivé
(drift rétabli par `pm-task-sync` sur l'enfant).

---

## [1.20.2] - 2026-06-01

### Ajouté — Règle de sécurité prod : consentement explicite obligatoire

Dans § « Cycle dev → test → MEP », workflow MEP : aucune commande susceptible de
modifier/casser la **production** (merge vers `prod_branch`, `git pull`/`reset`/
`checkout` sur un serveur prod, upgrade/migration de module, vidage de cache prod,
restart de service, écriture de fichier prod) ne doit être **exécutée sans
consentement explicite de l'humain pour l'action précise**. L'agent inspecte (lecture
seule), propose la commande exacte, attend le feu vert ; un accord ne vaut pas pour les
étapes suivantes. Un arbre de prod sale ou une source de déploiement divergente sont
des signaux d'arrêt.

> Note : les entrées [1.20.0] et [1.20.1] (bumps faits en sessions parallèles) manquent
> dans ce changelog — à backfiller par leurs auteurs.

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
