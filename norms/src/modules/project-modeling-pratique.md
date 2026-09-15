> 📂 **Module `project-modeling-pratique` — quand lire ceci :** je modélise un projet qui en implémente un autre (socle décliné par client) · je pose ou je répare `implements` / `implemented_by`.
> **Outils :** `pm-doctor`, `meta.yml` · **Préchargé par :** *(personne — ouvert à la demande)*.

Détail sorti de `project-modeling` (RM3037) pour tenir le budget de contexte : l'existence du lien et son
effet sur la cascade restent dans le module préchargé.

## Relation « implémentation » entre projets (implements / implemented_by) — v1.38.0

Distincte du partage cross-client ci-dessus. Un projet peut être l'**implémentation**
d'un projet **général**, à la manière d'une classe qui implémente une interface : le
projet général définit des **procédures, templates, conventions et assets réutilisables**,
le projet implémentation les **applique** à un contexte précis (un client, une instance).

La relation est **plusieurs-à-plusieurs** : un projet peut implémenter **plusieurs**
projets généraux à la fois (ex: une instance Dolibarr cliente implémente *à la fois*
`iprospective/infrastructure` **et** le projet produit Dolibarr général), et un projet
général peut être implémenté par plusieurs enfants. Les deux champs sont donc des **listes**.

| Champ | Sens | Côté |
|---|---|---|
| `implements: [<entité>/<projet>, ...]` | Liste des projets généraux que ce projet implémente | déclaré côté **implémentation** (ex: `cliente/infra` → `[iprospective/infrastructure]`) |
| `implemented_by: [<entité>/<projet>, ...]` | Liste des projets qui implémentent celui-ci | déclaré côté **général** (ex: `iprospective/infrastructure` liste ses projets infra clients) |

Comme `used_by_clients`/`provided_by`, ces deux champs sont **redondants par
construction** (lecture dans les deux sens) ; la cohérence est validée par `pm-doctor.py`
(à venir). Source de vérité = le **frontmatter** `project/overview.md`, pas
l'arborescence. Le chemin canonique reste `paths.project`. Listes vides = `[]`.

**Ne pas confondre avec `provided_by`** : `provided_by` modélise un **livrable**
(un projet — typiquement `product` — dont *le résultat* est consommé par plusieurs
clients) ; `implements` modélise une relation **interface ↔ implémentation** (le projet
enfant *réapplique les procédures/outils* du général à son contexte). Les deux peuvent
coexister sur un même projet.

**Cas d'usage canoniques :**
- **Projets infra client** → implémentent `iprospective/infrastructure`
  (`implements: iprospective/infrastructure`). Le projet général centralise l'outillage
  de supervision, les recettes réseau/stockage, les runbooks ; chaque infra client les
  applique. Se **cumule** avec la détection « projet infra » (slug/nom `infra` ou aspect
  `hosting`/`infrastructure`) qui, elle, conditionne le ticket `008-infra-analysis`
  (voir « Tâches de bootstrap »).
- **Instances produit client** (ex: une instance **Dolibarr** d'un client) →
  implémentent le projet produit général (`<product>/<projet>`).

**Conséquences opérationnelles :**
- **Où poser l'asset ?** Un asset (script, sonde, template, runbook) **réutilisable
  cross-contexte** se dépose dans le **repo du projet général**, pas dans le repo
  enfant. Exemple vécu : `clientb/infra` implémente `iprospective/infrastructure` —
  la sonde `probe-mail-stack.sh` et les scripts Sieve, réutilisables pour tous les
  clients, ont été déposés dans le repo **général** alors que le ticket de travail
  (RM1835) vivait dans l'enfant. Critère : **réutilisable par d'autres
  implémentations → général ; spécifique à ce contexte → enfant.**
- **Ticket cross-projet.** Un besoin **générique** découvert chez un client se crée
  comme ticket dans le projet **général** (et non dans l'enfant), relié au ticket
  enfant d'origine via `relates`. Le travail spécifique au client reste dans l'enfant.

**Pas de cascade d'aspects** : comme pour le cross-client, `implements` est
**déclaratif** (découverte de l'outillage commun + procédure de placement des assets) ;
il **ne déclenche aucun héritage** de frontmatter ni d'aspects. La cascade reste
mono-client (un projet n'hérite que de son `client:`).

### Aspects — cahier des charges dynamique

Le **cahier des charges** d'un projet est éclaté en plusieurs fichiers (aspects).
Cette approche évite le fichier monolithique illisible et permet d'enrichir
progressivement la connaissance du périmètre. **Deux emplacements** depuis la
privsep (RM2043), selon le discriminant *« a un filet de réconciliation, ou pas »* :

- **`project/`** — aspects **canoniques** consommés par l'outillage : `overview.md`
  (obligatoire, frontmatter + index) et `environments.md`. Couche `mathieu-pm`
  **stricte**, mutation **via `mmi-pm` uniquement**, **hors** wiki-sync.
- **`docs/`** — aspects **libres** (roadmap, data-model, orchestrator, specs, CDC…) :
  **wiki-syncés** (fold-back / merge 3-way) donc sûrs à éditer en direct ;
  group-writable `mathieu`. C'est `docs/` que `pm-wiki-sync` scrute.

**Règles :**
- `overview.md` est **obligatoire** — il porte le frontmatter et un index des aspects
- Tout autre aspect est **optionnel** ; un aspect **libre** se range dans **`docs/`**
  (un `*.md` libre laissé dans `project/` est signalé en erreur par `pm-doctor`)
- L'agent qui charge le contexte lit **tous** les fichiers de `project/` **et** `docs/`
- Les templates d'aspects sont dans `templates/aspects/{domaine}/{aspect}.md`

**Cascade des aspects :**
Un aspect peut exister au niveau client ET au niveau projet. L'agent lit les deux.
Le projet précise/surcharge le client sur les points en contradiction.

Exemple :
- `{entity_client_dir}/hosting.md` : "Tous nos sites sont hébergés chez OVH par défaut"
- `{docs_dir}/hosting.md` : "Ce projet est sur AWS pour des raisons spécifiques"
→ Pour ce projet, l'agent applique AWS (override).
