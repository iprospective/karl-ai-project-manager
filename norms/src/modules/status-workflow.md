> 📂 **Module `status-workflow` — quand lire ceci :** je change un statut · je prends une tâche · fin de dev/routing test · un ticket me revient · machine d'états · phase d'étude.
> **Outils :** `pm-task-status-update`, `redmine-fetch-updates` · **Préchargé par :** worker-dev, worker-analyst, orchestrateur.

## Passe agent-testeur indépendante (`requires_agent_test`)

À la fin d'un dev (`en_cours` terminé), le workflow canonique passe par `a_tester_dev`
(test par un **agent/humain testeur ≠ le dev**) avant `a_tester_demandeur`. Cette passe
n'est pas toujours nécessaire (artillerie lourde) — un champ par tâche la **conditionne** :

- **Champ tâche** `requires_agent_test` : `default` (défaut) | `oui` | `non` | `demander`.
- **Défaut projet** : `defaults.requires_agent_test` dans la config projet (`overview.md`).
  Si absent → **défaut système : `non`**.
- **Côté Redmine** : CF **27** « AI Test par agent » (énumération `Oui`/`Non`/`Demander`,
  value ids 39/40/41 ; cf. `redmine.reference.yml :: agent_test_values`). **Non
  sélectionné = `default`** (hérite). Le frontmatter MD fait foi pour l'agent ;
  `pm-task-sync` peut le rafraîchir depuis le CF.

**Résolution + routing** en fin de dev (`requires_agent_test` tâche → si `default`, défaut
projet → si absent, `non`) :

| Valeur résolue | Transition depuis `en_cours` |
|---|---|
| `oui` | → `a_tester_dev` (passe agent-testeur indépendante, attribué à un testeur ≠ dev) |
| `non` | → `a_tester_demandeur` (**bypass**, attribué au demandeur) |
| `demander` | l'agent **demande au demandeur** quelle voie prendre, puis applique |

Un agent en mode non interactif qui tombe sur `demander` (ou ne peut pas résoudre) **reste
en `en_cours`** et le signale plutôt que de trancher seul.

## Machine d'états

```
[a_etudier_chiffrer]
        │ estimation lancée
        ▼
[etude_chiffrage_en_cours]
        │ étude/CDC + chiffrage finis      │ abandonné / hors périmètre
        ▼                                  ▼
[etude_chiffrage_a_valider] (→ demandeur)  [ferme]
        │ validé par le demandeur   ▲ retour demandeur (ajustements)
        │                           └──────────────┐
        ▼                                          │
   [a_faire]                          [etude_chiffrage_en_cours]
        │ démarrage (+ création branche <RMid>-<desc>)
        ▼
   [en_cours] ◄────────────────────────────────────┐
        │ dev terminé                              │
        ▼                                          │
[a_tester_dev] ──── problèmes ───► [a_corriger] ───┤ corrections faites
        │ test dev OK                              │
        ▼                                          │
[a_tester_demandeur] ── rejet ─────────────────────┤
        │ validé (MR branche→dev, CF GIT PR, merge)
        ▼                                          │
    [a_mep]                                        │
        │ MR dev→preprod + déploiement preprod     │
        ▼                                          │
    [en_mep] ──── régression preprod ──────────────┘
        │ tests preprod OK + MR preprod→prod + pull prod   (2 branches : MR dev→prod)
        ▼
    [ferme]

[en_pause]  ⇄  depuis/vers tout état actif (blocage tiers ; reprend à l'état précédent)
[a_tester_demandeur] ──► [ferme]  (ticket sans code à déployer ; close_reason: resolu)
[en_cours] ──► [a_tester_demandeur]  (bypass passe agent-testeur : requires_agent_test=non ; cf. § dédiée)
```

Règle : **toute transition vers `ferme` requiert un `close_reason`.**
Le workflow complet (branches, envs, MEP) est décrit en § *Cycle de
développement → test → mise en production*.

### Transitions valides

| De | Vers | Condition |
|---|---|---|
| `a_etudier_chiffrer` | `etude_chiffrage_en_cours` | `assigned_to` renseigné |
| `etude_chiffrage_en_cours` | `etude_chiffrage_a_valider` | CDC + `estimate.*` complets → soumis au demandeur (ré-attribution `author`) |
| `etude_chiffrage_a_valider` | `a_faire` | validé par le demandeur → prêt à coder |
| `etude_chiffrage_a_valider` | `etude_chiffrage_en_cours` | retour demandeur (ajustements étude/chiffrage) |
| `etude_chiffrage_{en_cours,a_valider}` | `ferme` | `close_reason` requis |
| `a_faire` | `en_cours` | création branche `<RMid>-<desc>` + CF `GIT Branche` |
| `en_cours` | `a_tester_dev` | dev terminé + `requires_agent_test` résolu à `oui` |
| `en_cours` | `a_tester_demandeur` | dev terminé + `requires_agent_test` résolu à `non` (bypass passe agent-testeur) ; `demander` → demandeur tranche |
| `en_cours` | `a_etudier_chiffrer` | périmètre modifié |
| `a_tester_dev` | `a_tester_demandeur` | test dev OK |
| `a_tester_dev` | `a_corriger` | problèmes (note dans journal) |
| `a_tester_demandeur` | `a_mep` | validé : MR branche→`integration_branch` (CF `GIT PR`) puis mergée |
| `a_tester_demandeur` | `a_corriger` | rejet (note dans journal) |
| `a_tester_demandeur` | `ferme` | ticket sans code à déployer — `close_reason: resolu` |
| `a_mep` | `en_mep` | **3 branches** : MR `dev`→`preprod` mergée + `preprod` déployée. **2 branches** : `dev` déployée en staging |
| `en_mep` | `ferme` | tests preprod OK + **3 branches** : MR `preprod`→`prod_branch` / **2 branches** : MR `dev`→`prod_branch` + pull prod — `close_reason: resolu` |
| `en_mep` | `a_corriger` | régression preprod (note dans journal) |
| `a_corriger` | `en_cours` | — |
| `* (tout état actif)` | `en_pause` | blocage tiers ; reprend à l'état précédent au déblocage |
| `* (tout état)` | `ferme` | `close_reason` requis |
| `ferme` | `a_faire` | **réouverture** (RM2285) : note obligatoire motivant la réouverture ; `close_reason` purgé |

**Réouverture d'un ticket fermé (RM2285).** Un ticket `ferme` peut être rouvert
**uniquement vers `a_faire`** (retour au backlog — la reprise suit ensuite le flow
normal `a_faire → en_cours → …`, jamais de saut direct en réalisation). Conditions,
imposées par `pm-task-status-update` :
- **note obligatoire** motivant la réouverture (elle part en note Redmine et au journal) ;
- `close_reason` est **purgé** (`null`) — un ticket rouvert n'est plus « résolu » ;
- `status_history` **conserve le cycle précédent** (append-only) : l'historique
  fermeture(s)/réouverture(s) reste lisible.

Rouvrir n'est PAS le chemin pour « corriger une livraison qui régresse » — ça, c'est
`a_corriger` avant fermeture. On rouvre quand un ticket **déjà validé et clos** doit
reprendre du service (nouveau périmètre sur le même sujet → préférer un **nouveau
ticket lié** `relates` ; même périmètre non terminé en réalité → réouverture).

**Livraison en vérification — protocole de test + URL de test (RM2229).** Le
**protocole de test** (CF Redmine « Protocole de test », miroir frontmatter
`test_protocol`) se rédige **au fil de l'eau**, à chaque étape d'avancement du dev —
pas rétroactivement à la livraison : `pm-task-protocol <id> --set -/--append -`.
Au passage en `a_tester_dev`/`a_tester_demandeur`/`a_mep` : protocole non vide
(le garde-fou de `pm-task-status-update` avertit) et **`test_url` renseigné** —
automatique si l'env de session existe (`pm-env-session create` écrit frontmatter
+ CF « Environnement de test » ; le teardown les vide), sinon manuel. Le testeur
doit savoir **quoi tester et où** sans relire tout le ticket (fiche de revue cockpit).

**Précondition de fermeture — sous-tâches.** Un ticket qui possède des
**sous-tâches** ne peut passer en `ferme` que lorsque **toutes ses sous-tâches sont
elles-mêmes `ferme`**. C'est imposé côté Redmine (la transition du parent est
**refusée** tant qu'un enfant reste ouvert) — corollaire de la règle d'orchestration
« un parent passe en `ferme` uniquement quand tous ses enfants directs sont `ferme` »
(module `collaboration`, § *Propagation de complétion*).

**Précondition de fermeture — relations bloquantes.** De même, un ticket **bloqué par**
une relation `blocks` / `precedes` (= NORMS `depends_on`) ne peut être fermé tant que le
ticket **source** reste ouvert — refus tout aussi **silencieux** que pour les sous-tâches.
Ce n'est **ni** un problème de droit, **ni** de workflow, **ni** de tracker. (Vécu sur
RM1813, bloqué par #1816 / #1814 / #1848 encore ouverts.)

**Outil de diagnostic — `pm-task-blockers.py <id>` (réflexe).** Dès qu'une transition vers
`ferme` (ou tout statut) est **refusée silencieusement**, lancer
`scripts/pm-task-blockers.py <id>` : il liste en un coup les **relations bloquantes
ouvertes** (blocks/precedes) ET les **sous-tâches ouvertes**, et dit **quoi clôturer
d'abord** (`--json` pour l'outillage). À préférer au diagnostic manuel ci-dessous.

> **Comment ça se manifeste (piège diagnostique).** Le refus est **silencieux** : le
> `PUT` renvoie 204, la note éventuelle est bien postée, mais le `status_id` est
> **ignoré** — le statut reste inchangé. `redmine-post-note` / `pm-task-status-update`
> rapportent alors « *permission 'Edit issues' manquante* », ce qui est une
> **interprétation** (statut inchangé après PUT), **pas la vraie cause**. Ne pas
> conclure à un problème de droits, de rôle ou de tracker (« Evolution » et « Tâche »
> ont les **mêmes** droits). Diagnostic autoritatif :
> `GET /issues/<id>.json?include=allowed_statuses` (si `18 Fermé` est absent → transition
> non permise) puis `?include=children,relations` (un enfant non clos **ou** une relation bloquante ouverte = le blocage ; `pm-task-blockers.py` automatise les deux). Remède :
> fermer/détacher l'enfant d'abord, ou — si le contenu de référence doit rester sur le
> parent — créer une **sous-tâche « cadrage » clôturable** (cf. encadré ci-dessous).

> **Conséquence de modélisation (à anticiper).** Le **contenu** d'un livrable de
> cadrage (CDC, étude, décision d'architecture) peut tout à fait **vivre dans la
> description du parent** quand il sert de **pilote** (référence « north-star » pour les
> enfants) — c'est même souhaitable. Ce qui ne doit pas reposer sur le parent, c'est la
> **clôture** de ce livrable : le parent restant bloqué ouvert tant que ses sous-tâches
> d'implémentation ne sont pas fermées, créer une **sous-tâche dédiée** (« cadrage / CDC »)
> que l'on clôt pour acter l'achèvement de l'étude. Principe : **dissocier le contenu de
> référence (description du parent, pilote) de l'unité clôturable (sous-tâche).** Le parent
> reste un **conteneur** dont la fermeture suit celle de ses enfants.

### Phase d'étude / qualification : audit, analyse & CDC *avant* de coder — v1.25.0

Les deux premiers statuts du workflow ne sont **pas** une simple file d'attente
administrative : ils matérialisent une **phase de travail à part entière**,
réalisée **avant d'écrire la moindre ligne de code**. Aucun ticket non trivial ne
passe directement à `a_faire` / `en_cours` sans être passé par cette phase.

| Statut NORMS | Redmine | Sens |
|---|---|---|
| `a_etudier_chiffrer` | A étudier / Qualifier (8) | Le ticket est entré mais pas encore analysé : **file d'attente de la qualification**. |
| `etude_chiffrage_en_cours` | Etude/CDC en cours (14) | **Phase active** : audit de l'existant, analyse du besoin, rédaction du CDC, découpage, estimation. |
| `etude_chiffrage_a_valider` | Etude/CDC à valider (21) | **Étude finie, soumise au demandeur** : le livrable (CDC + chiffrage) attend sa validation. Ticket ré-attribué au demandeur. |

**Contenu de l'étude** (`etude_chiffrage_en_cours`) :
- **Audit** — lire le code, l'infra, les contraintes ; cartographier l'existant et les pièges.
- **Analyse** — clarifier le besoin réel, les cas limites, les non-objectifs.
- **CDC** — produire / mettre à jour le cahier des charges (aspect projet, cf. § *Aspects*).
  C'est le **livrable** de cette phase pour tout ticket non trivial.
- **Découpage & chiffrage** — sous-tickets éventuels, `estimate.*` complet.

**Fin de l'étude : soumettre au demandeur (obligatoire) — v1.28.0.** Quand l'étude
est terminée (CDC rédigé, `estimate.*` complet), l'agent **ne passe pas directement
à `a_faire`** : il passe le ticket en **`etude_chiffrage_a_valider`**, ce qui le
**ré-attribue au demandeur** (author ; author == karl → Manager IA — même résolveur
que `a_tester_demandeur`). Le demandeur valide le périmètre + le chiffrage avant tout
développement. C'est le pendant amont du `a_tester_demandeur` aval.

**Sorties de phase** :
- `etude_chiffrage_en_cours → etude_chiffrage_a_valider` — étude finie, CDC + `estimate.*` complets → soumis au demandeur (ré-attribution automatique).
- `etude_chiffrage_a_valider → a_faire` — validé par le demandeur → prêt à coder.
- `etude_chiffrage_a_valider → etude_chiffrage_en_cours` — retour du demandeur : ajustements d'étude / de chiffrage demandés.
- `etude_chiffrage_{en_cours,a_valider} → ferme` — abandonné / hors périmètre (`close_reason` requis).

Un ticket de type `audit`, `research` ou `design` peut **rester** dans cette phase
jusqu'à sa fermeture : le livrable *est* l'étude, pas du code. À l'inverse, un ticket
en `en_cours` dont le périmètre change repasse en `a_etudier_chiffrer` (cf. transitions).

**Synchronisation Redmine** : ces trois statuts sont mappés (§ *Mapping NORMS → Redmine*,
ids **8**, **14** et **21**) et pilotés par les skills/scripts habituels — `mmi-pm-task-status-update`
(`pm-task-status-update.py`), `redmine-post-note.py --norms-status`. On ne fixe **jamais**
un statut Redmine « en dur » : on passe toujours par le mapping NORMS.

### Transitions « assignee-only » — v1.31.0

Dans le workflow Redmine, **certaines transitions ne sont autorisées que si le ticket
est assigné au compte API courant** (karl, id 79). C'est notamment le cas des deux
transitions qui *soumettent au demandeur* :

- `etude_chiffrage_en_cours → etude_chiffrage_a_valider` (Redmine **14 → 21**) ;
- `* → a_tester_demandeur` (Redmine → **9**).

Or ces transitions s'accompagnent justement d'une **réattribution au demandeur**. Si
l'on pousse `status_id` **et** `assigned_to_id` (= demandeur) dans le **même PUT** alors
que le compte API n'est pas (encore) l'assigné, Redmine évalue le workflow sur l'assigné
**avant** mise à jour → la transition est **refusée silencieusement** : `HTTP 204` mais
statut inchangé (faux diagnostic « permission *Edit issues* manquante »).

**Règle d'exécution (gérée automatiquement par `redmine-post-note.py`)** : avant un PUT
de statut, si le statut cible n'est pas dans `allowed_statuses` et que le compte API
n'est pas l'assigné courant, **s'auto-assigner d'abord** (PUT préalable) pour débloquer
la transition, **puis** faire le PUT principal (statut + réattribution finale au
demandeur). Conséquence visible : un journal d'assignation supplémentaire (→ karl, puis
→ demandeur). Ne **jamais** contourner en fixant le statut « en dur ». Le mapping inverse
Redmine→NORMS (`pm-task-sync.py`) doit connaître l'id **21** sous peine de laisser le MD
périmé sur `etude_chiffrage_en_cours`.

### Tâche

- `redmine_id: <int>` est **obligatoire** dans le frontmatter
- Le nom de fichier `RM{id}_{titre}.md` **doit correspondre** à `redmine_id`
  (cohérence vérifiée par le validateur)
- Pas de tâche MD sans ticket Redmine préexistant

### Projet

- `redmine.project_id: <slug>` est **obligatoire** dans `project/overview.md`
- `redmine.subprojects: [slug, slug, ...]` est optionnel — liste les sous-projets
  Redmine rattachés (utile quand plusieurs sous-projets concernent ce même projet MD)

### Workflow multi-tour (reprise après notes du demandeur)

Quand un ticket revient à un worker (réattribution, ou statut passe à `a_corriger`),
le worker doit ne traiter que les **nouveautés** depuis sa dernière vue du ticket.

Champs du frontmatter de la tâche :
- `redmine_last_journal_id: <int>` — id du dernier journal Redmine consulté
- `redmine_last_checked_at: <str iso>` — timestamp du dernier check

Protocole de reprise :
1. `scripts/redmine-fetch-updates.py --issue <id>` → affiche tous les journaux
   postérieurs à `redmine_last_journal_id`, et met à jour ce champ
2. Lire les nouvelles notes + changements d'attributs (status, assignation, priorité…)
3. Décider : corrections à faire ? livrables à compléter ? ticket déjà résolu ?
4. Appliquer le travail demandé selon le protocole worker standard
5. Resoumettre via `redmine-post-note.py --norms-status a_tester_demandeur` (qui
   réattribue automatiquement au demandeur)

Le champ `redmine_last_journal_id` est initialisé par `redmine-fetch-task.py` à la
**dernière entrée existante** au moment du fetch, pour que le worker ne traite que
ce qui se passe **après** sa prise en charge.

**Persistance dans le journal** : `redmine-fetch-updates.py` appende chaque nouveau
journal Redmine récupéré au fichier `.log.md` de la tâche (append-only, conforme
NORMS). Format d'entrée :

```markdown
## YYYY-MM-DDTHH:MM — Redmine #<journal_id> — <auteur Redmine>
Source : Redmine (sync via redmine-fetch-updates)

Changements :
- `field` : `old` → `new`
- ...

Note (verbatim) :
> ligne 1
> ligne 2
```

Le worker peut ainsi retrouver l'historique complet des échanges (côté Redmine ET
côté agent) en relisant simplement le `.log.md`, sans avoir à re-fetcher l'API.

### Synchronisation des statuts MD ↔ Redmine (obligatoire)

**Tout changement de `status` dans le frontmatter d'une tâche doit être répercuté
sur le ticket Redmine correspondant**, dans le même cycle de travail.

L'agent (ou l'orchestrateur) qui modifie le `status` MD doit :
1. Mettre à jour le frontmatter (`status`, `status_history`, `updated`)
2. Appender l'événement dans `.log.md`
3. Poster une note Redmine + changer le `status_id` correspondant
   (typiquement via `scripts/redmine-post-note.py --norms-status <statut>`)

**Demandeur effectif = `author_id` natif Redmine** (cf. RM1735) :

Le ticket porte son demandeur via le champ standard `author_id`. À la création
par `pm-task-add.py`, un PUT immédiat ajuste `author_id` :
- **Par défaut** → Manager IA (`pm.config.yml :: ia.default_manager.redmine_id`)
- **Avec `--initiator-agent`** → karl (id=79) : audits autonomes, bootstrap
  automatique, tâches initiées par un agent

Le CF `Demandeur` (id=12) est **déprécié** (cf. RM1739 pour la suppression
définitive sur l'instance). Plus aucun script ne le consulte.

**Règle d'attribution Redmine** :
- Passage en `etude_chiffrage_a_valider` → ré-attribuer au **demandeur** (author) :
  l'étude / CDC / chiffrage sont finis et soumis à sa validation. **Même résolveur
  que `a_tester_demandeur`** (author ≠ karl → author ; author == karl → Manager IA).
  Appliqué automatiquement par `pm-task-status-update.py`.
- Passage en `a_tester_dev` → ré-attribuer à un **testeur ≠ le dev** (agent ou
  humain), pour un test indépendant en env `test`. Manuel via `--assign-to <id>`
  pour l'instant ; l'orchestrateur routera vers un worker-test quand il sera en place.
- Passage en `a_tester_demandeur` → ré-attribuer au **demandeur** (author).
  Résolveur appliqué par `pm-task-status-update.py` :
  1. `author == karl` (cas légitime --initiator-agent) → **Manager IA**
  2. `author ≠ karl` avec email accessible → cet `author`
  3. fallback (email inaccessible) → Manager IA
- Passage en `a_mep` → ré-attribuer au **responsable MEP / intégration** (par défaut
  Manager IA ou orchestrateur ; configurable par projet).
- Passage en `en_mep` → ré-attribuer au **testeur humain** chargé de la vérification
  en preprod (étape 3 du workflow MEP, cf. § Cycle dev → test → MEP).
- Passage en `a_corriger` → ré-attribuer au **worker** précédent (manuellement pour
  l'instant via `--assign-to <id>`, automatisé quand l'orchestrateur sera en place).
- Passage en `en_pause` → **conserver** l'attribution courante (la tâche reste
  possédée, juste sortie des files actives).
- Passage en `ferme` → conserver l'attribution courante.

> Note : `a_tester_verifier` (≤ v1.18.0) est **déprécié**, remplacé par le couple
> `a_tester_dev` / `a_tester_demandeur`. Les scripts l'acceptent encore en lecture
> et le normalisent vers `a_tester_demandeur` (rétrocompat).

**Manager IA** (cf. RM1734) : humain qui supervise les agents (karl + futurs),
reçoit la notif mail à chaque livraison, se voit assigner les tickets
`a_tester_demandeur` quand l'auteur est karl. Configuré dans `pm.config.yml` :

```yaml
ia:
  default_manager:
    redmine_id: 5
    email: mathieu@iprospective.fr
    name: Mathieu Moulin
```

V2 prévue : cascade par projet (`ia.managers:` par `paths.project`) et/ou
champ `ia_manager:` dans le frontmatter de `project/overview.md`.

### Prise en charge d'une tâche : `en_cours` ⇒ auto-assignation (obligatoire) — v1.12.0

**Règle** : un agent qui commence à travailler sur une tâche doit, dans le **même
mouvement** :

1. Passer le `status` de la tâche à `en_cours` (côté Redmine + frontmatter MD + log)
2. **S'assigner le ticket Redmine** (champ `assigned_to`) si ce n'est pas déjà le cas

Les deux opérations sont **indissociables**. Une tâche `en_cours` sans
`assigned_to` cohérent est un état invalide : `en_cours` signifie « un agent
nommément identifié est en train de faire le travail maintenant ». Pas
d'`en_cours` flottant.

Cette règle vaut **même hors orchestrateur** (mode interactif Claude Code) : si
un humain demande à l'agent de bosser sur RM1234 et que le ticket n'est ni à
`en_cours` ni assigné à l'agent, l'agent fait lui-même les deux opérations avant
de démarrer le travail effectif.

**Symétrie avec la `Vérification initiale` de [worker-common.md](../agents/worker-common.md)** :
ce qu'un worker orchestré vérifie passivement (status + assigné à soi), un agent
en mode interactif l'établit activement au démarrage.

**Implémentation** : `pm-task-status-update.py` **couple** status + assignation —
quand la cible est `en_cours`, il auto-assigne au user Redmine de l'agent courant
(résolu via `pm.config.yml :: agents.<id>.redmine_id`, défaut karl=79). Aucun PUT
manuel à faire ; `--no-assign` pour outrepasser.

**Mapping NORMS → Redmine (instance iprospective)** — après consolidation RM1742 :

Statut Redmine (un seul terminal `Fermé`) :

| NORMS | Redmine | id |
|---|---|---|
| `nouveau` | Nouveau | 1 |
| `a_etudier_chiffrer` | A étudier / Qualifier | 8 |
| `etude_chiffrage_en_cours` | Etude/CDC en cours | 14 |
| `etude_chiffrage_a_valider` | Etude/CDC à valider | 21 |
| `a_faire` | A Faire | 12 |
| `en_cours` | En cours | 2 |
| `a_tester_dev` | A tester/vérifier dev | 19 |
| `a_tester_demandeur` | A tester/vérifier demandeur | 9 |
| `a_mep` | Résolu/Validé/A MEP | 3 |
| `en_mep` | MEP/Tester en preprod | 20 |
| `en_pause` | Attente retour / en pause | 13 |
| `a_corriger` | A corriger/finir | 11 |
| `ferme` (toutes raisons) | Fermé | **18** |

`a_tester_verifier` (déprécié) → lu comme `a_tester_demandeur` (id 9).
`a_mep` (Résolu/Validé/A MEP, id 3) est un statut **non terminal** (validé par le
demandeur, mergé dans l'intégration, en file de MEP) — à ne pas confondre avec
`ferme`.

`nouveau` (Nouveau, id 1) est le **statut d'entrée** : `pm-task-add.py` crée par
défaut un ticket en `nouveau` (ticket déposé, non encore trié/engagé), avec
`author_id` posé mais **sans `assigned_to`** (pas encore pris en charge). Le tri
vers `a_faire` / `a_etudier_chiffrer` / `en_cours` se fait ensuite (manuellement
ou à la création via `pm-task-add.py --status <statut>`, qui crée en `nouveau`
puis transitionne via `pm-task-status-update.py` pour bénéficier du couplage
NORMS — assignation, note, `status_history`). Un ticket reste légitimement en
`nouveau` tant qu'il n'a pas été engagé ; ce n'est pas un état invalide.

Raison de fermeture (CF `Raison Fermé`, id=11, format enumeration) — valeurs :

| NORMS `close_reason` | CF Raison Fermé | value_id |
|---|---|---|
| `resolu` | Résolu | 10 |
| `wont_fix` / `hors_perimetre` | Rejeté | 11 |
| `abandonne` | Abandonné | 12 |
| `doublon` | Déjà existant | 13 |
| `invalide` | Pas un bug / rien à faire | 14 |

Note : les anciens statuts terminaux `Résolu/Fermé` (5), `Rejeté` (6),
`Pas un bug / Déjà existant` (7), `Abandonné` (10) sont **dépréciés** —
à désactiver/supprimer en UI Redmine. Attention à ne pas les confondre avec le
nouveau `Résolu/Validé/A MEP` (id 3, `a_mep`), qui est **non terminal**.

## Lien Redmine ↔ MD (obligatoire)

Toute entité du système (tâche, projet) **doit** être reliée à son équivalent Redmine.
Cette règle est vérifiée par le validateur.

