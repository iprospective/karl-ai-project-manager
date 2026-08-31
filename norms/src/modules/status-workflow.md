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
[a_tester_demandeur] ── rejet ─────────────────────┤  (env DEV : le demandeur
        │ validé par le demandeur sur DEV          │   valide sur l'env de dev)
        │ (MR branche→dev, CF GIT PR, merge)       │
        ▼                                          │
[a_tester_preprod] ── régression préprod ──────────┤  (env PRÉPROD : déploiement
        │ recette préprod OK                       │   préprod qui suit dev, recette)
        ▼                                          │
    [a_mep]                                        │  (validé + en file de MEP —
        │ MR préprod→prod + pull prod              │   PAS encore déployé)
        │ (2 branches : MR dev→prod)               │
        ▼                                          │
    [en_mep] ──── régression prod ─────────────────┘  (EN PROD : déployé, dernière
        │ vérif prod OK                                vérif avant fermeture)
        ▼
    [ferme]

[en_pause]  ⇄  depuis/vers tout état actif (blocage tiers ; reprend à l'état précédent)
[a_tester_demandeur] ──► [ferme]  (ticket sans code à déployer ; close_reason: resolu)
[a_tester_demandeur] ──► [a_mep]  (bypass préprod : projet SANS env préprod → dev→prod direct)
[en_cours] ──► [a_tester_demandeur]  (bypass passe agent-testeur : requires_agent_test=non ; cf. § dédiée)
```

> **⚙ Refonte RM2893 (en cours de livraison — 2026-08-31).** Le tronçon aval a été
> redéfini pour lever une confusion : le statut ne disait pas *où est le code*. Nouvelle
> sémantique par environnement :
>
> | Statut | Env | Sens |
> |---|---|---|
> | `a_tester_demandeur` | **dev** | le demandeur valide sur l'env de dev |
> | `a_tester_preprod` (**nouveau, optionnel**) | **préprod** | merge dev + déploiement préprod, recette ; **sauté** si le projet n'a pas d'env préprod (→ `a_tester_demandeur` va direct à `a_mep`) |
> | `a_mep` | — | validé, en file de MEP — **pas encore déployé** |
> | `en_mep` (**redéfini**) | **prod** | déployé en prod, **dernière vérif avant fermeture** |
>
> Avant : `en_mep` = « tester en préprod » et le déploiement prod se faisait *en sortant*
> d'`en_mep`. Désormais le déploiement prod se fait **en entrant** dans `en_mep`, qui
> devient l'état « en prod, en attente de fermeture ». Motivation : le flux *deploy-first*
> (déployer puis faire valider) n'avait aucun statut exprimant « en prod + à fermer »
> (constat session 2026-08-28 : RM2575/2576/2885/2886 tous « en prod » mais posés en
> `a_tester_demandeur`). Mapping Redmine, attribution et routing outillage mis à jour dans
> le même lot (cf. § Mapping et `pm-task-status-update`). Les deux statuts Redmine existent
> déjà : `a_tester_preprod` = id **20** « MEP/Tester en preprod » ; `en_mep` = id **22**
> « MEP/Vérifier en prod » (aucune création/renommage).

Règle : **toute transition vers `ferme` requiert un `close_reason`.**
Le workflow complet (branches, envs, MEP) est décrit en § *Cycle de
développement → test → mise en production*.

### Flux court micro-tâches — v1.61.0 (RM2369, CDC RM2316 § S8)

**Critère** : `estimate.time_minutes ≤ 30` **et** pas de livrable code (audit
éclair, doc courte, correction de données, assistance). Constat d'audit
(RM2275) : sur ces tickets la cérémonie atteignait 40–59 % du coût.

**Séquence** — mêmes statuts, mêmes notes (templatées § traceability), zéro
infrastructure inutile :

1. `pm-task-take <id> --no-branch` — en_cours + assignation, PAS de branche ni
   d'env de session ;
2. travail + entrée `.log.md` (le sémantique reste obligatoire) ;
3. `pm-task-deliver <id> --summary -` — critères/protocole/routage inchangés.

Travail déjà fait au moment de la création → `pm-task-add --retro` (le ticket
traverse la machine d'états en un appel). Un micro-ticket qui grossit en cours
de route (code nécessaire) repasse au flux standard : `pm-task-take <id>`
(idempotent) crée branche + env à ce moment-là.

### Tâche

- `redmine_id: <int>` est **obligatoire** dans le frontmatter
- Le nom de fichier `RM{id}_{titre}.md` **doit correspondre** à `redmine_id`
  (cohérence vérifiée par le validateur)
- Pas de tâche MD sans ticket Redmine préexistant

### Projet

- `redmine.project_id: <slug>` est **obligatoire** dans `project/overview.md`
- `redmine.subprojects: [slug, slug, ...]` est optionnel — liste les sous-projets
  Redmine rattachés (utile quand plusieurs sous-projets concernent ce même projet MD)

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
- Passage en `a_tester_preprod` (RM2893, **optionnel**) → ré-attribuer au **responsable
  recette préprod** (par défaut le **demandeur** — même résolveur que `a_tester_demandeur` ;
  configurable par projet). Étape sautée si le projet n'a pas d'env préprod
  (`a_tester_demandeur` → `a_mep` direct).
- Passage en `a_mep` → ré-attribuer au **responsable MEP / intégration** (par défaut
  Manager IA ou orchestrateur ; configurable par projet).
- Passage en `en_mep` (RM2893, **redéfini = en prod, dernière vérif avant fermeture**) →
  ré-attribuer au **demandeur** (author) pour la vérification finale en prod avant clôture
  (même résolveur que `a_tester_demandeur`). ⚠ Ancienne sémantique « testeur préprod »
  dépréciée.
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
| `a_tester_preprod` (RM2893) | MEP/Tester en preprod | 20 |
| `a_mep` | Résolu/Validé/A MEP | 3 |
| `en_mep` (RM2893) | MEP/Vérifier en prod | 22 |
| `en_pause` | Attente retour / en pause | 13 |
| `a_corriger` | A corriger/finir | 11 |
| `ferme` (toutes raisons) | Fermé | **18** |

> **RM2893 — migration du mapping (2026-08-31).** Les deux statuts Redmine existaient déjà
> et leurs libellés collent : **aucune création ni renommage**. Seul changement d'id :
> `en_mep` passe de **20 → 22** (« MEP/Vérifier en prod »), et le statut **20**
> (« MEP/Tester en preprod ») devient `a_tester_preprod`. Les tickets déjà au statut 20
> (préprod) sont donc réinterprétés `en_mep`→`a_tester_preprod` — sémantiquement exact,
> ils restent au même statut Redmine ; leur frontmatter MD se réaligne au prochain
> `pm-task-sync`. ⚠ Vérifier que les transitions de workflow Redmine (par rôle/tracker)
> autorisent bien l'entrée en 20 depuis `a_tester_demandeur` et en 22 depuis `a_mep`
> (sinon le PUT échoue silencieusement — cf. `knowledge/redmine/gotchas.md`).

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

