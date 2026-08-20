> 📂 **Module `project-modeling` — quand lire ceci :** je crée/range un projet ou une entité · partage cross-client · relation implements · je documente un aspect (CDC) · je note les contacts d'un client.
> **Outils :** `pm-client-new`, `pm-doctor` · **Préchargé par :** worker-analyst.

## Types d'entités

Le dossier `paths.entities_dir` (par défaut `{projects_root}/clients`) regroupe
**3 types d'entités**, distingués par le champ `type` du frontmatter
`{entity_client_dir}/overview.md` :

| `type` | Sémantique | Exemples |
|---|---|---|
| `client` (défaut) | Entité commerciale tierce qui commande des prestations | `lemathou` (perso/freelance Mathieu), `pisceen`, `calicote` |
| `product` | Écosystème produit dont iprospective développe des modules (génériques) ou maintient une instance interne | `redmine`, `dolibarr`, `prestashop`, `symfony` |
| `self` | Entité où l'on est client de soi-même : outils internes, scripts propres, projets perso non commerciaux | `iprospective` (entreprise freelance), `lemathou` aussi (projets perso de Mathieu) |

Cohérent avec l'arborescence workspace : `/zfs/workspaces/<entité>/` existe au même niveau
pour chaque entité, qu'elle soit `client`, `product` ou `self`.

**Règle d'arbitrage** lorsqu'un projet pourrait vivre sous plusieurs entités (ex: un
module Dolibarr générique utilisé par plusieurs clients) :

- Si **commandé/financé par un client** → sous ce client (`paths.project` avec `entity=<client>`)
- Si **générique** (marketplace, communauté, usage interne propre) → sous l'écosystème produit (`paths.project` avec `entity=<product>`)
- Si **outil interne** non rattaché à un produit tiers → sous `self` (`paths.project` avec `entity=iprospective`)

Suivre l'engagement de livraison et la responsabilité des données.

## Contacts d'un client — `meta.yml :: contacts[]` (v1.69.0, RM2702)

Les personnes d'un client vivent dans le `meta.yml` de son core
(`.mmi-pm-client/meta.yml`), et **uniquement** là. Écriture par
`pm-client-contact.py` (`add` / `list` / `set` / `remove` / `mark-internal` /
`import-redmine`) — jamais à la main (tripwire #1).

```yaml
contacts:
  - last_name: Dupont              # NOM de famille
    first_name: Claire             # prénom
    email: claire@exemple.fr       # identifie la fiche (clé de `set` / `remove`)
    phone: "+33 6 12 34 56 78"     # CHAÎNE : le « + » et les zéros de tête comptent
    role: technique                # owner | decideur | technique | facturation | autre
    title: Gérant                  # fonction EN CLAIR — `role` est une catégorie, pas un titre
    internal: true                 # posé AUTOMATIQUEMENT sur nos propres adresses
```

Deux pièges, tous deux rencontrés en production :

- **`internal`** marque **nos** adresses (`iprospective.fr`…). Le gabarit de création
  en pose une chez **chaque** client : elle n'identifie donc aucun client et ne doit
  jamais servir à l'identifier — router un email entrant sur cette base enverrait tout
  notre courrier chez un client au hasard (cf. routage RM2669).
- Une fiche **entièrement vide** (`{name: "", email: "", role: owner}`) est un résidu
  de gabarit, pas un contact : les outils l'ignorent.

Une **boîte de service** (« Service informatique », « comptabilité ») est un contact
légitime sans nom propre : on renseigne `title` + `email`, sans `last_name`/`first_name`.

Le champ historique `name` (nom complet en un bloc) reste **lu en repli** tant que
toutes les fiches n'ont pas été reprises ; les nouvelles écritures utilisent
`last_name` / `first_name`.

> Un **annuaire de contacts indépendant** des clients (une personne rattachée à
> plusieurs clients/projets, avec un rôle par rattachement) est à l'étude — RM2703.
> Tant qu'il n'existe pas, `contacts[]` reste la source unique.

## Partage cross-client (used_by_clients / provided_by)

Un projet rangé sous une entité (`product` notamment) peut être **utilisé par plusieurs
clients**. Plutôt que de dupliquer le projet ou de jouer avec des symlinks à la main,
on utilise deux champs dans le frontmatter `project/overview.md` :

| Champ | Sens | Côté |
|---|---|---|
| `used_by_clients: [<slug>, ...]` | Liste des entités qui consomment ce projet | déclaré côté **fournisseur** (ex: module Dolibarr générique liste `pisceen, calicote, calyclay`) |
| `provided_by: <client>/<projet>` | Pointeur vers le projet fournisseur | déclaré côté **consommateur** (ex: un projet client qui s'appuie sur le module) |

Ces deux champs sont **redondants par construction**, pour permettre la lecture dans les
deux sens sans scan inverse coûteux. `scripts/pm-doctor.py` valide la cohérence des paires.

**Source de vérité** : le frontmatter, pas l'arborescence filesystem. Le chemin
canonique d'un projet est toujours `paths.project` (`entity=<owner>`,
`project=<projet>`).

**Vue cross-client (navigation humaine uniquement)** : un dossier `paths.entity_used_dir`
(par défaut `{entity}/projects_used`, au même niveau que `entity_projects_dir`, **pas**
un sous-dossier) peut contenir des symlinks relatifs vers les projets fournisseurs.
Ces symlinks sont **générés** par un script (`pm sync-views`) à partir des
`used_by_clients[]`, jamais édités à la main.

**Règles cross-client :**
- La cascade des aspects reste **mono-client** : un projet hérite uniquement de son
  client `client:`, jamais des clients listés dans `used_by_clients[]`.
- Tous les chemins dans le frontmatter (`outputs[]`, etc.) sont **canoniques**
  (résolus via `paths.project` avec l'`entity` propriétaire), jamais via `entity_used_dir`.
- Les scripts d'itération doivent utiliser `find -P` (ou `! -type l`) et **ne pas suivre
  les symlinks** dans `projects_used/`. Sinon double-comptage.
- L'édition se fait toujours via le chemin canonique. `projects_used/` est en lecture
  pour les humains.
- Suppression d'un usage : retirer le client de `used_by_clients[]` côté fournisseur ET
  `provided_by` côté consommateur si présent. `pm sync-views` nettoie les symlinks
  orphelins.

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
| `implements: [<entité>/<projet>, ...]` | Liste des projets généraux que ce projet implémente | déclaré côté **implémentation** (ex: `abatik/infra` → `[iprospective/infrastructure]`) |
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
  enfant. Exemple vécu : `calyclay/infra` implémente `iprospective/infrastructure` —
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

