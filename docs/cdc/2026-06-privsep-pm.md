# CDC — Durcissement privsep du système PM

> **Statut** : design figé (2026-06-18), consigné. Implémentation = sous-tickets de **RM1902**.
> **Voir aussi** : RM1902 (chapeau), RM2032 (verrou), RM1680 (dispatcher/CLI), RM1993/RM1947 (layout `docs/`), RM1821 (wiki-sync), RM1906 (multi-tenant).

## 1. Contexte & objectif

L'outil PM (`.mmi-pm-core` + les `.mmi-pm`/`.mmi-pm-client` co-localisés) est aujourd'hui entièrement `mathieu`-writable → un agent ou un humain qui *code* peut, par accident ou dérapage, corrompre la **structure** et les **métadonnées** PM (« pétouilles »). Objectif : **séparation de privilèges** (privsep) — confiner les modifications PM derrière l'outil, pour que la **cohérence de la structure PM soit assurée par construction**.

Trois bénéfices : (1) anti-accident ; (2) confinement des agents ; (3) **prérequis** de l'ouverture multi-tenant / client-facing (RM1906), où la frontière devient une vraie barrière de confiance.

## 2. Modèle 3-couches (analogie service Linux)

C'est le pattern classique d'un démon Linux bien packagé (PostgreSQL, nginx, GitLab, systemd `User=`/`ProtectSystem=strict`) : root possède le code + la config ; un **user de service dédié** fait tourner le démon et possède **ses données** ; les autres users **ne touchent jamais ses fichiers** — ils passent par le service.

| Couche | User | Possède / fait |
|---|---|---|
| **Code + config-outil** | `root` | code, `norms/`, `templates/`, `pm.config.yml`, `.git` — **immuable**, MAJ par `mmi-pm core update` (sudo) |
| **Secrets** | `root` | `.env` 640, groupe partagé en **lecture** (mathieu + mathieu-pm) |
| **Service PM** | **`mathieu-pm`** (`KARL_SUDO_USER`) | fait tourner l'**applicatif** (web-ui, orchestrateur) ; **crée/synchronise** clients-projets ; possède la **structure PM** (`.mmi-pm`/`.mmi-pm-client`, index `projects/`), `var/`, les **réglages opérationnels** |
| **Agent / humain** | **`mathieu`** (`KARL_USER`) | **code** dans les workspaces ; **lit** config/tâches ; **ne peut pas** réécrire la structure ni les métadonnées PM |

`.env` lisible par les deux : `mathieu-pm` est ajouté au **groupe `mathieu`** (le plus privilégié voit le moins privilégié → pas d'escalade) ; `.env` = `root:mathieu` 640.

## 3. Décision centrale

**Toute opération PM passe par l'unique point d'entrée `bin/mmi-pm`, re-exec en `mathieu-pm` via `sudo` NOPASSWD.** `mathieu` n'a **aucune** capacité directe autre que **coder dans un projet**. Toute la gestion de projet — structure, métadonnées, tâches, état — passe par les scripts PM, en `mathieu-pm`.

Comme **aucune mutation ne peut contourner l'outil** (la donnée appartient à `mathieu-pm`, seul `mmi-pm` y écrit), la structure ne peut pas **dériver** vers un état incohérent. C'est l'analogie base-de-données : on ne corrompt pas le schéma en éditant les fichiers derrière le dos du serveur, parce qu'on **ne peut pas** y toucher.

## 4. Critère « sensible » & cartographie des domaines

**Sensible** (→ sudo `mathieu-pm`) si l'opération coche ≥ 1 : **rayon d'impact** (> 1 projet, l'index) ; **parité externe** (sync Redmine/GitLab) ; **confiance/sécurité** (secrets, config de comportement/droits). Sinon → non sensible.

| Domaine | Sensible ? | Owner/runner |
|---|---|---|
| 1. Namespace/structure (créer/déplacer/sync client·projet, index, co-location) | OUI (rayon+parité) | `mathieu-pm` |
| 2. Config & secrets (`.env`, config-outil, réglages opérationnels) | OUI (confiance) | `root` / `mathieu-pm` |
| 3. État tâche & parité Redmine (statut, liens, métriques, sync) | OUI (parité) | `mathieu-pm` (via outil) |
| 4. Contenu d'un projet (tasks/, aspects canoniques, prose) | selon zone (cf. §5) | mixte |
| 5. Runtime/session (`var/sessions`, ticks, time) | bas (état service) | `mathieu-pm` |
| 6. Lecture/report (list, show, dashboard, doctor) | non | tous |

**Décision** : on ne fait **aucune exception de gray-zone** — *tout* le PM passe par `mmi-pm`/`mathieu-pm`, y compris l'état de tâche (§3). Le NOPASSWD supprime la friction qui aurait justifié de laisser le workflow courant à `mathieu`.

## 5. Frontière des données : `.mmi-pm` (mathieu-pm) vs `docs/` (mathieu)

Le vrai discriminant pour « éditable directement par `mathieu` » n'est pas « prose vs structuré » mais **« a un mécanisme de réconciliation, ou pas »** :

- Les fichiers **synchronisés vers le wiki Redmine** sont sûrs à éditer librement **parce que `pm-wiki-sync` fait un fold-back / merge 3-way** (RM1821) — deux éditions concurrentes se réconcilient.
- Les fichiers de **`tasks/`** (`RM*.md` + **`.log.md`**) n'ont **aucun filet** : état en parité stricte avec l'issue Redmine + journal d'audit → édition libre = corruption.

**Conséquence (layout)** — pour garder `.mmi-pm/` **100 % `mathieu-pm`** (ACL triviale, zéro exception interne) :

```
<client>/<projet>/
├── .mmi-pm/        100 % mathieu-pm — tasks/, project/{overview,environments,aspects canoniques}, meta.yml   [mutation via mmi-pm]
├── docs/           mathieu-éditable — doc wiki LIBRE, réconciliée par le sync                                 [édition directe]
├── repos/ envs/    mathieu (le code)
```

- **Restent dans `project/` (canoniques, `mathieu-pm`)** : `overview.md`, `environments.md` (+ whitelist d'aspects structurés consommés par l'outillage).
- **Partent vers `docs/` (libres, `mathieu`)** : tous les autres aspects-docs (roadmap, data-model, orchestrator, migration-plan, etc. — ≈ 9 fichiers épars).
- **Propriété élégante** : la frontière de droits = **le périmètre du wiki-sync** ; elle se **dérive** du manifeste de sync (si un fichier entre/sort du sync, sa permission suit).
- L'**opération de sync** (`mmi-pm wiki sync`) reste sensible (touche Redmine) → `mathieu-pm` ; `mathieu` édite le fichier, l'outil réconcilie (`mathieu-pm` est dans le groupe `mathieu` → lit/écrit les fichiers partagés pour le fold-back).
- Même logique au **niveau client** (`.mmi-pm-client`) : overview client wiki-synced → `docs/` ; `memory/`/`projects_used/` → `mathieu-pm`.

## 6. Patron de sécurité — dispatcher défensif

Le NOPASSWD reporte **toute** la frontière de sécurité sur `mmi-pm` → conçu **fail-closed** dès le départ (sinon réécriture à la bascule multi-tenant) :

- **Whitelist stricte** verbe par verbe ; inconnu → refus. Pas de pass-through vers un shell.
- **Validation d'arguments typée** par verbe ; flag inattendu → refus ; séparateur `--`.
- **Confinement de chemin** : tout arg-chemin `realpath`-é doit tomber dans les racines autorisées ; rejet `..`/symlink qui s'échappe.
- **Jamais d'entrée utilisateur vers un shell** ; exec en tableaux. **Durcir `git`/`glab`** (neutraliser `-c core.pager/alias`, `GIT_*`, `--upload-pack`, `protocol.ext`…).
- **Env propre** : sudoers `env_reset` + `secure_path` ; ignorer `GIT_*`/`PYTHON*`/`LD_*`/`IFS`.
- **Cible figée** : impossible de viser un autre user que `mathieu-pm`.
- **Journal d'audit** de chaque invocation privilégiée.
- **Endgame** : la forme *vraiment* blindée = un **service `mathieu-pm` long-vivant via socket Unix** (requêtes structurées) → supprime la surface « args de sudo ». Converge avec la web-ui/orchestrateur. Le NOPASSWD-CLI est l'intérim.

## 7. `mmi-pm edit` — capacité d'édition confinée

Éditer un fichier PM `mathieu-pm` (overview, environments, aspect, corps de tâche) **ergonomiquement** et **sûrement**. Principe : une **capacité à usage unique** — « écrire *ce* fichier, rien d'autre, d'aucune autre façon ».

- **Surface minimale** : `mmi-pm edit <chemin-cible>`, **contenu sur stdin** uniquement (pas de `--from` = pas de primitive de lecture privilégiée ; pas de `--into`/`--move`/`--exec`).
- **JAMAIS d'éditeur interactif en `mathieu-pm`** (`EDITOR` privilégié = shell-out = trou). L'agent produit le contenu en `mathieu`, le soumet en stdin.
- **Cible confinée** : whitelist de zones+types (`docs/`, `project/{overview,environments,aspects}` ; refus `tasks/`, `.log.md`, `meta.yml`, `.git`, `.env`, hors-zone) ; anti-traversée (`realpath` parent ∈ racine ; refus si `realpath ≠ logique`) ; **anti-symlink** (`openat` + `O_NOFOLLOW`, `lstat` = fichier régulier) ; **anti-TOCTOU** (vérifier+écrire sur le **même fd**).
- **Pas de patch générique** (un diff contient des chemins → autre fichier) : remplacement du contenu complet du seul fd ouvert.
- **Validation par type, SÛRE** (`yaml.safe_load`, jamais d'`eval`/tag/hook) ; lock optimiste + commit+push du **seul** fichier.
- Garde-fous : refus sur `.log.md` (→ `pm-task-comment`) et sur le frontmatter d'état d'un `RM*.md` (→ `pm-task-status-update`).

Ce patron (**surface minimale + cible confinée par fd + fail-closed**) est le modèle de *chaque* verbe privilégié ; `edit` est le plus exposé car il écrit du contenu arbitraire.

## 8. Séquencement & sous-tickets (de RM1902)

L'ordre est contraint : **on ne peut pas verrouiller `.mmi-pm` en `mathieu-pm` tant que des docs `mathieu`-éditables y vivent.**

0. **Migration `docs/` + refactor scripts** (prérequis) — move aspects libres `project/→docs/` sur les `.mmi-pm` existants ; adapter `pm-wiki-sync` (scope source), `pm_paths` (`docs_dir`), scaffolding (`pm-project-new`/`-bootstrap`/`-client-new`), `pm-doctor`, `templates/aspects`, NORMS (`project-modeling`/`structure-reference`). Outil `pm-docs-migrate` idempotent/dry-run/réversible.
1. **`mmi-pm edit`** (capacité confinée, §7).
2. **Dispatcher défensif** (§6) — whitelist/validation/confinement/audit.
3. **`core-lock` 3-niveaux + sudoers NOPASSWD** (RM2032) — chown root/mathieu-pm/mathieu, `.env` `root:mathieu` 640, `var/` `mathieu-pm:mathieu` 2775, `projects/` selon décision finale ; `mmi-pm` re-gated.

Multi-tenant (RM1906) : durcir le NOPASSWD (virer le `*`, whitelist d'args, bascule socket) — la frontière devient *load-bearing*.
