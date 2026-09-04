> 📂 **Module `status-workflow-pratique` — quand lire ceci :** je cherche la transition exacte permise depuis un statut · je qualifie/chiffre en phase d'étude · je rédige un CDC / une proposition d'implémentation · une transition m'est refusée alors que je ne suis pas l'assigné · un ticket revient avec des notes du demandeur.
> **Outils :** `pm-task-status-update --list-next`, `redmine-fetch-updates` · **Préchargé par :** *(personne — ouvert à la demande)*.

# Statuts — table des transitions et cas particuliers

Détaché de `status-workflow.md` par RM2582. La table des transitions est une
**référence** : le KERNEL impose déjà de la demander à l'outil
(`pm-task-status-update --list-next`) plutôt que de la deviner — la porter en
permanence dans le contexte de tous les workers ne servait à rien. Les règles
obligatoires (machine d'états, synchronisation MD ↔ Redmine, auto-assignation à
la prise) sont restées dans `status-workflow.md`.

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
| `a_tester_demandeur` | `a_tester_preprod` | *(RM2893, si préprod)* validé sur **dev** : MR branche→`integration_branch` (CF `GIT PR`) mergée + déploiement préprod |
| `a_tester_demandeur` | `a_mep` | *(projet SANS préprod)* validé : MR branche→`integration_branch` (CF `GIT PR`) puis mergée |
| `a_tester_demandeur` | `a_corriger` | rejet (note dans journal) |
| `a_tester_demandeur` | `ferme` | ticket sans code à déployer — `close_reason: resolu` |
| `a_tester_preprod` | `en_mep` | *(RM2920)* instruction **« mets en prod »** (préprod testée + temps de tester la MEP) : MEP prod faite dans la foulée |
| `a_tester_preprod` | `a_mep` | *(RM2920)* instruction **« preprod ok »** : mise en **file de MEP** (déploiement prod plus tard) |
| `a_tester_preprod` | `a_corriger` | régression préprod (note dans journal) |
| `a_mep` | `en_mep` | déployé en **PROD** : **3 branches** MR `preprod`→`prod_branch` / **2 branches** MR `dev`→`prod_branch` + pull prod |
| `en_mep` | `ferme` | *(RM2893 : `en_mep` = en prod)* vérif **prod** OK — `close_reason: resolu` |
| `en_mep` | `a_corriger` | régression **prod** (note dans journal) |
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
- **Proposition d'implémentation** — l'esquisse technique, dans le CF 31 via
  `pm-task-implementation` (§ dédiée ci-dessous). **Obligatoire dès que l'étude débouche
  sur du code**, quelle que soit la taille du développement.

**Fin de l'étude : soumettre au demandeur (obligatoire) — v1.28.0.** Quand l'étude
est terminée (CDC rédigé, **proposition d'implémentation** posée, `estimate.*`
complet), l'agent **ne passe pas directement à `a_faire`** : il passe le ticket en **`etude_chiffrage_a_valider`**, ce qui le
**ré-attribue au demandeur** (author ; author == karl → Manager IA — même résolveur
que `a_tester_demandeur`). Le demandeur valide le périmètre + le chiffrage avant tout
développement. C'est le pendant amont du `a_tester_demandeur` aval.

**Sorties de phase** :
- `etude_chiffrage_en_cours → etude_chiffrage_a_valider` — étude finie, CDC + proposition d'implémentation + `estimate.*` complets → soumis au demandeur (ré-attribution automatique).
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
#### La proposition d'implémentation — v2.10.0 (RM2563)

Le CDC répond au **quoi** (besoin, périmètre, critères d'acceptation) et le chiffrage au
**combien**. Il manquait le **comment** : l'esquisse technique que l'audit vient de
produire. Sans elle, l'agent qui reprend le ticket en `a_faire` **refait l'audit** —
travail payé deux fois, et refait moins bien, puisqu'il repart sans les conclusions déjà
acquises.

**Où elle vit.** Champ canonique : le CF Redmine **31 « Proposition d'implémentation »**
(texte long, visible sur la fiche) ; miroir local dans le frontmatter `implementation`
(c'est le miroir que lit la fiche de revue du cockpit — karl-agent ne lit que le local).
Outil unique : **`pm-task-implementation`** (`--set` / `--append`), jamais d'écriture à la
main dans l'un ou l'autre. Un CDC rédigé avant l'existence du CF, qui porte l'esquisse en
section `## Implémentation` du corps, se migre par `--from-description` (en masse :
`pm-cf-mirror-backfill --adopt-sections` — le corps est **conservé**, rien n'est effacé).

**Synchronisation.** PM → Redmine à l'écriture ; Redmine → PM à chaque `pm-task-sync`,
pour rattraper une saisie faite dans l'UI web. Un CF vide ne remet **jamais** le miroir
local à zéro.

**Contenu attendu.** Les rubriques sans objet se taisent : on ne les remplit pas pour
faire nombre.

| Rubrique | Ce qu'on y met |
|---|---|
| Modèle de données | tables / colonnes / champs ajoutés ou modifiés — nom + type + rôle en une ligne. Pas le DDL complet. |
| Composants | classes / modules / scripts à créer ou modifier, un rôle par ligne. Pas les signatures. |
| **Points d'insertion** | `fichier:fonction` où le code se greffe dans l'existant. **La rubrique la plus précieuse** : c'est le fruit le plus périssable de l'audit, celui qui coûte le plus cher à retrouver. |
| Vues / UI | écrans, colonnes, filtres impactés. |
| Flux & déclencheurs | ce qui appelle quoi — hook, trigger, cron, webservice. |
| Migration / initialisation | backfill, scripts rejouables, ordre des opérations. |
| Pièges identifiés | les surprises de l'audit : règle métier contre-intuitive, incohérence de l'existant, contrainte d'environnement. |

**Niveau de détail.** Assez pour ne pas refaire l'audit, pas assez pour figer le code :
**l'esquisse oriente, elle ne prescrit pas.** L'implémenteur garde la main sur le détail
et peut s'en écarter — en le justifiant dans le `.log.md`. Ordre de grandeur : **15 à 40
lignes**, aucun bloc de code sauf un DDL, une requête ou une signature réellement
décisifs. L'excès inverse est un échec symétrique : une esquisse qui devient une spec
détaillée alourdit la phase d'étude et confisque le travail de l'implémenteur.

**Quand elle est exigée.** Dès que l'étude **débouche sur du code** — **sans exemption
pour les petits développements**. Sur un dev simple elle fera cinq lignes, mais
elle sera là : c'est précisément là qu'on se dispense d'écrire ce qu'on a compris, faute
d'enjeu apparent. Seul un ticket `audit` / `research` / `documentation` dont le livrable
**est** l'étude en est dispensé — et si cette étude débouche sur un ticket de code, c'est
ce ticket-là qui porte la proposition.

**Pourquoi une obligation, pas un conseil.** Le rationnel n'est pas la taille de la tâche
mais l'**asymétrie de compétence** : l'étude est menée par le modèle le plus fort,
l'implémentation revient souvent à un modèle plus économe — ou à un humain pressé. La
proposition d'implémentation est le canal par lequel le raisonnement du modèle fort
survit à ce transfert. Ce qui n'est pas écrit à ce moment-là est perdu. Cas déclencheur : **RM2560**
(calicote/dolibarr), dont le CDC livré ne portait aucune des conclusions techniques de
l'audit sous forme actionnable.

**Condition de sortie.** Une étude sans proposition d'implémentation (hors tickets
dispensés) n'est **pas** finie : le passage en `etude_chiffrage_a_valider` ne doit pas
être demandé. `pm-task-status-update.py` émet un **avertissement non bloquant** sur cette
transition quand elle manque — même forme que le garde-fou « protocole de test » (RM2229).
La garde lit le frontmatter `implementation`, et **accepte aussi** une section
`## Implémentation` dans le corps, pour ne pas crier sur les CDC d'avant.

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
