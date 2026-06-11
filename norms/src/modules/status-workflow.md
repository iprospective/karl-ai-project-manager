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
        │ dev déployée en preprod                  │
        ▼                                          │
    [en_mep] ──── régression preprod ──────────────┘
        │ tests OK + merge dev→prod + pull prod
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
| `a_mep` | `en_mep` | `integration_branch` déployée en preprod |
| `en_mep` | `ferme` | tests preprod OK + merge `integration_branch`→`prod_branch` + pull prod — `close_reason: resolu` |
| `en_mep` | `a_corriger` | régression preprod (note dans journal) |
| `a_corriger` | `en_cours` | — |
| `* (tout état actif)` | `en_pause` | blocage tiers ; reprend à l'état précédent au déblocage |
| `* (tout état)` | `ferme` | `close_reason` requis |

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

