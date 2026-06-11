---
schema_version: "0.1.0"
updated: 2026-06-11
status: draft
tracks: RM1922
relates: RM1923
---

# CDC — Restructuration de NORMS (RM1922)

Cahier des charges **complet et exhaustif** de la factorisation de NORMS. Le contrat
de maintenance (principes, conventions, doctor) vit dans
[`MAINTAINING.md`](MAINTAINING.md) ; **ce document** porte la **cartographie de
relocalisation** (où va chaque chose) + la **trigger map** du KERNEL + le plan
d'exécution. Ensemble ils forment le CDC.

Lire d'abord `MAINTAINING.md` §3-§5 (zéro perte / couverture comportementale / chaîne
règle→skill→script) : les règles ci-dessous **les appliquent**.

---

## 1. Cartographie exhaustive section → destination

**Les 34 sections de niveau `##` de NORMS.md (+ sous-sections structurantes) sont
toutes affectées.** C'est la garantie de non-omission : aucune section sans
destination. Légende destination — `K-T` = tripwire complet dans KERNEL ; `K-R` =
ligne-déclencheur dans KERNEL + détail en module ; `mod:X` = module ; `HORS` = sort
du runtime (gouvernance) ; `role:X` = addendum de rôle.

| # | Section NORMS (ligne) | Dest. | Obligation(s) portée(s) | Déclencheur KERNEL (si K-R) | Outil |
|---|---|---|---|---|---|
| 1 | Configuration globale (8) | HORS | secrets en `.env`, jamais en dur | — | — |
| 2 | Config des chemins pm.config.yml (28) | mod:structure-ref + K-R | jamais de concaténation/hardcode de chemin | « je résous un chemin PM » | `pm_paths.PMConfig` |
| 3 | Skills PM distribution (82) | HORS | skill PM versionné dans `skills/`, jamais perso | « je crée un skill PM » | `pm-skills-sync` |
| 4 | **Outillage obligatoire en session (108)** | **K-T** | toute op d'état tâche/branche/repo/Redmine via outil dédié, **jamais à la main** ; trou sans outil = à combler | (tripwire permanent) | tous les `pm-*` |
| 5 | Types d'entités (141) | mod:project-modeling | arbitrage client/product/self | « je crée/range un projet ou une entité » | `pm-client-new` |
| 6 | Partage cross-client (165) | mod:project-modeling | maj `used_by_clients`/`provided_by`, `find -P`, édition canonique | « un projet sert plusieurs clients » | `pm-doctor`*, `pm-sync-views`* |
| 7 | Relation implements (202) | mod:project-modeling | placement asset réutilisable→général ; ticket générique→général | « un projet implémente un général / je place un asset » | `pm-doctor`* |
| 8a | Structure des dossiers — arbo (257) | mod:structure-ref | — (référence) | — | — |
| 8b | **Commit + push systématique (333)** | **K-T** | stage par chemins explicites (jamais `git add .`), relire le set stagé, ne committer **que ses propres modifs**, push immédiat | (tripwire permanent) | `mmi-pm-git-*`** |
| 8c | Remote GitLab / MR / gotchas (392) | mod:git-mep | livraison par MR, gogs déprécié, gotcha `%2F`→id | « je push / crée une MR » | `glab`, `mmi-pm-git-*`** |
| 8d | Branche par ticket (424) | K-R + mod:git-mep | branche `<RMid>-<slug>` jamais sur l'intégration ; CF GIT Branche | « je commence à coder un ticket » | `mmi-pm-git-*`** |
| 8e | Projets versionnés / branche active (450) | mod:git-mep | choix base de branchement, demander si doute | « projet versionné / je choisis la base » | — |
| 8f | Workspace symlinks `.mmi-pm` (484) | mod:structure-ref | 2 symlinks absolus, ignorer en itération | « je crée/répare le lien workspace↔PM » | `pm-sync-links`** |
| 8g | Aspects — CDC dynamique (545) | mod:project-modeling | lire **tous** les fichiers `client/`+`project/` ; cascade override | (l'« ordre de lecture » est en K via Cascade) | — |
| 8h | Environnements (566) | mod:environments | connexion via `ssh_alias` ; `staging`=`preprod` | « je me connecte à / référence un env » | — |
| 8i | **Secrets Vaultwarden (628)** | **K-T** + mod:environments | secret **jamais** commité/loggué/sur disque ; jamais demander le master pw | (tripwire) ; « je manipule un secret » | `resolve-secret.sh` |
| 9 | **Cascade et héritage (690)** | **K** (colonne vertébrale) | ordre de lecture du contexte (4 niveaux) | (onboarding) | — |
| 10 | Fichiers auto-générés (715) | role:summarizer | — | (rôle summarizer) | — |
| 11 | Ordonnancement par ROI (725) | mod:roi-pricing | — | (rôle orchestrateur) | `priority.py` |
| 12 | Nommage des fichiers (738) | **K** (court) | `RM{id}_{slug}.md` | (convention) | — |
| 13 | Lien Redmine↔MD (747) | **K-T** + mod:project-creation | `redmine_id` obligatoire + nom de fichier cohérent (intégrité) ; flow création+memberships (détail) | (tripwire intégrité) | `pm-project-new` |
| 14 | Tâches de bootstrap (819) | mod:project-creation | templates par défaut, infra→008 | « je crée un projet PM » | `pm-project-bootstrap` |
| 15 | Workflow multi-tour reprise (880) | K-R + mod:status-workflow | ne traiter que les nouveautés depuis `last_journal_id` | « un ticket me revient (a_corriger/réattrib) » | `redmine-fetch-updates` |
| 16 | **Sync statuts MD↔Redmine (922)** | **K-T** | tout changement de statut → Redmine + MD + log, même cycle | (tripwire) | `pm-task-status-update` |
| 17 | **Prise en charge en_cours⇒auto-assign (986)** | **K-T** | `en_cours` ⇒ auto-assignation indissociable | (tripwire) | `pm-task-status-update` |
| 18 | Mapping NORMS→Redmine ids (1021) | mod:redmine-reference | — (référence ids) | — | — |
| 19 | Maj description Redmine (1070) | K-R + mod:redmine-hygiene | description vivante ; checklist & `done_ratio` au fil de l'eau ; note si desc change | « le ticket a une checklist / desc périmée / done_ratio bouge » | `pm-task-description-update` |
| 20 | Flux création de tâches (1147) | mod:project-creation | — | (cf. #14) | `pm-task-add` |
| 21 | **Schéma frontmatter Tâche (1167)** | **K** | champs obligatoires/conditionnels | (intégrité) | `validate-task` |
| 22 | ROI assisté IA (1184) | K-R + mod:roi-pricing | estimer à la création **et** à la prise si absent ; report temps/tokens par commit | « je crée / je prends un ticket sans estimation » ; « je commit » | `pm-task-add`, `pm-task-tick`, `pm-task-report`** |
| 23 | Liens entre tâches (1374) | K-R + mod:task-links | symétrie des miroirs ; sens des dépendances | « je lie / dépends / parent deux tickets » | `pm-task-link` |
| 24 | Hiérarchie parent/enfant (1402) | mod:task-links | ne jamais éditer `parent_task`/`sub_tasks` à la main | (sous le déclencheur #23) | `pm-task-link`, `pm-task-add --parent` |
| 25 | Sync config Redmine (1430) | mod:redmine-reference | revérifier les ids avant session d'intégration / périodiquement | « avant une session touchant Redmine / périodique » | `redmine-config-check` |
| 26 | Filtrage IA (1504) | K-R + mod:redmine-reference | tout ticket PM porte CF IA ; pas de MD sans CF IA | « je crée un ticket » | `pm-task-add`, `redmine-tag-ia` |
| 27 | Passe agent-testeur (1584) | mod:status-workflow | routing `requires_agent_test` ; `demander`→ne pas trancher seul | « fin de dev, je route vers test » | `pm-task-status-update` |
| 28 | **Machine d'états (1610)** | **K (principe+enum)** + mod:status-workflow | jamais de statut « en dur » ; transitions via l'outil | « je change un statut » → interroger les cibles | `pm-task-status-update --list-next`** |
| 29 | Valeurs énumérées (1743) | **K** (type/status/priority/close_reason) + mod (reste) | close_reason obligatoire si `ferme` ; target_env∈environments | (intégrité) | — |
| 30 | Journal .log.md (1783) | **K** | format append-only, jamais éditer rétroactivement | (tripwire) | — |
| 31a | Collaboration — ownership/locking (1794) | **K-T** | propriété exclusive du fichier ; optimistic locking (`updated`) ; `.log.md` append-only | (tripwire) | — |
| 31b | Rôles / sous-tâches multi-niveaux (1804) | mod:collaboration | orchestrateur seul écrivain des parents | (rôle orchestrateur) | — |
| 31c | Journalisation échanges humain (1925) | K-R + mod:collaboration | résumer au fil de l'eau les décisions/arbitrages | « un échange porte une décision sur la tâche » | — |
| 31d | Unité de traçabilité — étape significative (1939) | K-R + mod:traceability | commit + note Redmine + log à la frontière d'étape ; matrice « quand noter » | « je commit / je franchis une étape » | `pm-task-report`** |
| 31e | Référencer un commit (1979) | mod:traceability | citer SHA/URL commit dans l'entrée | (sous #31d) | — |
| 32 | Cycle dev→test→MEP (2000) | role:dev + mod:git-mep ; **encadré prod = K-T** | narratif release ; **aucune commande prod sans consentement explicite par action** | (K-T prod) ; « je livre / MEP » | `pm-task-status-update` |
| 33 | Architecture de déploiement (2093) | HORS | — (gouvernance) | — | — |
| 34 | Versionning des normes (2157) | HORS (→ MAINTAINING §12) | procédure anti-collision | — | — |

`*` outil à créer (RM1923 #2-#4). `**` outil à créer/compléter (RM1923 #1, #5, #6).

---

## 2. Trigger map consolidée du KERNEL (l'index exhaustif des déclencheurs)

Ce que le KERNEL expose pour qu'un worker **sache toujours quand ouvrir quoi**.
Chaque ligne = une **situation observable** → module (ou tripwire `K-T`). Tirée
intégralement de la colonne « Déclencheur » ci-dessus, dédoublonnée.

| QUAND (situation que l'agent reconnaît) | → ALORS | Outil |
|---|---|---|
| je résous un chemin PM | `pm_paths` (jamais de hardcode) | `PMConfig` |
| je modifie un fichier PM/workspace | **K-T** commit+push (stage explicite, propres modifs, push) | `mmi-pm-git-*`** |
| je commence à coder un ticket | mod:git-mep (branche `<RMid>-slug` + CF GIT Branche) | `mmi-pm-git-*`** |
| je push / crée une MR / projet versionné | mod:git-mep | `glab` |
| je change un statut de tâche | **K-T** sync + cibles via `--list-next` | `pm-task-status-update` |
| je prends une tâche (passage en_cours) | **K-T** auto-assignation + estimer si absent | `pm-task-status-update` |
| fin de dev / routing test | mod:status-workflow (`requires_agent_test`) | `pm-task-status-update` |
| un ticket me revient (a_corriger / réattribution) | mod:status-workflow (ne traiter que les nouveautés) | `redmine-fetch-updates` |
| le ticket a une checklist / desc périmée / done_ratio bouge | mod:redmine-hygiene | `pm-task-description-update` |
| je commit / franchis une étape significative | **K-R** note Redmine + log + métriques (matrice) | `pm-task-report`** |
| un échange porte une décision/arbitrage sur la tâche | **K-R** journaliser au fil de l'eau dans `.log.md` | — |
| je crée un ticket | CF IA auto + estimation initiale | `pm-task-add` |
| je crée un projet / entité PM | mod:project-creation (+ bootstrap, memberships) | `pm-project-new`, `pm-project-bootstrap` |
| un projet sert plusieurs clients / implémente un général | mod:project-modeling | `pm-doctor`*, `pm-sync-views`* |
| je crée/répare le lien workspace↔PM | mod:structure-ref | `pm-sync-links`* |
| je me connecte à / référence un env | mod:environments | — |
| je manipule un secret / credential | **K-T** jamais committer/logger + mod:environments | `resolve-secret.sh` |
| je lie / dépends / parent deux tickets | mod:task-links | `pm-task-link` |
| avant une session touchant Redmine / périodique | mod:redmine-reference (revérifier ids) | `redmine-config-check` |
| je touche à de la prod | **K-T** consentement explicite par action | — |
| je fais évoluer un paramètre canonique (type/ids/mappings) | **K-R** propagation source unique → consommateurs | — |

→ ~22 déclencheurs + une douzaine de tripwires permanents. **Couvre les 124 lignes
d'obligation** de NORMS (recensement par section §1). `pm-norms-doctor` vérifie qu'il
n'y a **aucune obligation de module orpheline** (sans déclencheur ici).

---

## 3. Inventaire des modules (couche B)

`structure-ref`, `git-mep` (sous-modules possibles `git/branch`, `git/mr`, `git/mep`,
`git/versioning`), `status-workflow`, `redmine-hygiene`, `redmine-reference`,
`roi-pricing`, `traceability`, `task-links`, `environments` (sous-module `secrets`),
`project-modeling`, `project-creation`, `collaboration`. **Non figé** : le nombre peut
croître / se sous-diviser (cf. MAINTAINING §7). Règle invariante : **une action = un
fichier ouvert**.

Préchargement par rôle (couche C) — inchangé vs plan RM1922 : worker-dev {git-mep,
status-workflow, redmine-hygiene, environments, traceability} ; worker-analyst
{status-workflow, redmine-hygiene} ; worker-db {git-mep, environments} ; worker-infra
{git-mep, environments, structure-ref} ; worker-design {redmine-hygiene} ;
orchestrateur {roi-pricing, task-links, status-workflow, collaboration} ; summarizer
{fichiers auto-générés}.

---

## 4. Livrables (RM1922)

1. `NORMS-KERNEL.md` — index exhaustif des déclencheurs + tripwires.
2. `norms/modules/**` — modules & sous-modules (détail verbatim + `tools:`).
3. `worker-{role}.md` enrichis — `loaded_modules`.
4. `pm-norms-assemble.py` — build `NORMS.md` par concaténation.
5. `MAINTAINING.md` — contrat (écrit, statut brouillon).
6. (RM1923) `pm-norms-doctor.py` + les 6 autres trous d'outillage.

---

## 5. Plan d'exécution (ordre)

1. **Filet d'abord** : `MAINTAINING.md` (fait) + `pm-norms-assemble.py` +
   `pm-norms-doctor.py`. Sans eux, on ne peut pas prouver la non-perte à mesure.
2. **Recensement** : geler la checklist des obligations (par la cartographie §1) ;
   `pm-norms-doctor` la prend comme oracle de couverture.
3. **Extraction itérative** : un module à la fois, verbatim ; après chaque module,
   `assemble` + `diff` (doit être vide hors dédup listés §1 MAINTAINING) + `doctor`.
4. **KERNEL** : rédiger l'index des déclencheurs (trigger map §2) + tripwires.
5. **Rôles** : déclarer `loaded_modules` par rôle.
6. **Calibrage à l'usage** : mesurer l'onboarding réel d'un worker-dev sur une vraie
   tâche ; rapatrier au KERNEL tout déclencheur/règle manquant trop souvent.

---

## 6. Critère de complétude du CDC (ce qui prouve « rien omis »)

- ✅ Les **34 sections** de NORMS ont une destination (§1).
- ✅ Les **~22 déclencheurs** couvrent les **124 lignes d'obligation** (§2).
- ✅ La **chaîne** déclencheur→module→skill→script est explicite (colonne Outil).
- ✅ Les **trous d'outillage** repérés sont tous tracés (`*`/`**` → RM1923).
- ✅ La **non-perte** est un test exécutable (`assemble`+`diff`, `doctor`), pas une
  promesse.
