---
schema_version: "0.1.0"
updated: 2026-06-11
status: draft
tracks: RM1922
---

# MAINTAINING.md — le « NORMS de NORMS »

Contrat de **structure et de maintenance** de NORMS. Décrit *comment NORMS est
organisé et comment on le fait évoluer sans le casser*. Distinct de NORMS.md, qui
décrit *comment on gère les tâches*.

> **Statut : brouillon.** Ce document fixe le contrat de la **structure cible**
> conçue sous RM1922 (factorisation de NORMS). Il devient actif quand le refactor
> est exécuté. Outil d'enforcement : `pm-norms-doctor.py` (RM1923, item 7).

---

## 1. Pourquoi cette structure existe

NORMS.md monolithique faisait **deux métiers contradictoires** dans un seul fichier :

1. **Spec canonique de gouvernance** (faire évoluer le système) — veut
   l'exhaustivité, le rationnel, l'historique des versions.
2. **Prompt runtime** injecté dans chaque agent worker — veut le strict minimum
   *just-in-time*.

Ces deux cibles s'optimisent à l'**inverse** : chaque règle ajoutée pour (1) taxe
le contexte de (2). À 2189 lignes / ~29k tokens lus à chaque invocation worker, le
coût était devenu structurel. La factorisation sépare les deux métiers.

---

## 2. La chaîne : du *savoir quand* au *faire*

```
KERNEL                  module / sous-module          skill            script
(savoir QUAND)    →     (savoir QUOI + QUEL skill) →  (capacité)  →    (exécutable)
index exhaustif         détail de la règle +          SKILL.md         pm-*.py
des déclencheurs        lien vers l'outil
```

- **KERNEL** = `norms/src/NORMS-KERNEL.md`. Lu par **tout** worker. Index **exhaustif
  des déclencheurs** + les tripwires complets (cf. §4).
- **Modules** = `norms/src/modules/*.md`. Chargés **à la demande**. Il peut y en avoir
  **beaucoup**, organisés en **sous-modules** imbriqués quand un domaine est riche
  (ex. `git/branch.md`, `git/mr.md`, `git/mep.md` sous un `git/`).
- **Méta-artefacts** (non assemblés) : `norms/src/manifest.yml` (ordre),
  `_frontmatter.txt`, `_original-frozen.md` (oracle de non-perte), `dedup-ledger.yml`.
- **Skills** = `skills/*/SKILL.md`. Une règle qui s'**exécute** nomme le skill qui
  la réalise.
- **Scripts** = `scripts/*.py`. Ce que le skill appelle.

> **Source de vérité = KERNEL + modules.** `NORMS.md` (document complet) est un
> **artefact GÉNÉRÉ** par concaténation (`pm-norms-assemble.py`) — **jamais édité à
> la main**. Le document entier continue d'exister, lisible d'un bloc, et il est
> *prouvablement* l'union des morceaux.

---

## 3. Principe 1 — ZÉRO perte d'information

Tout ce que contient NORMS est important. La factorisation est une **relocalisation
sans perte**, **pas un résumé** :

- Le détail intégral descend **verbatim** dans les modules. Le KERNEL ne fait que
  router et porter les tripwires.
- **Vérification = test, pas promesse** : `diff NORMS.md(ancien) ⟷ assemblé(nouveau)`
  doit être **vide**, sauf les dédoublonnages explicitement listés (cf. §8). Toute
  disparition non listée **fait échouer** le build (`pm-norms-doctor`).
- « Dédoublonner » = supprimer une info dite **deux fois à l'identique** (gardée une
  fois + cross-ref). « Simplifier » = meilleure **structure**, **jamais** moins de
  contenu.

---

## 4. Principe 2 — COUVERTURE comportementale (ne jamais rater un déclencheur)

NORMS documente des **directives à respecter**. Si une règle vit dans un module que
l'agent n'a **jamais ouvert**, elle est **silencieusement violée**. Le KERNEL est
donc l'**index EXHAUSTIF des déclencheurs**, pas une simple table de routage.

**Distinction fondatrice** : on sépare l'**existence + le déclencheur** d'une
obligation (TOUJOURS dans le KERNEL) de son **contenu détaillé** (peut descendre en
module). On ne diffère **jamais** la connaissance « *dans la situation X, il y a des
règles* » — seulement « *ce que disent exactement ces règles* ».

Chaque obligation de NORMS est représentée dans le KERNEL sous **l'une** des formes :

- **(T) Tripwire complet** — dangereux-si-raté **et** court : texte gardé **verbatim**
  dans le KERNEL.
- **(R) Ligne-déclencheur** — `QUAND <situation observable> → lis <module>`. Le détail
  descend, le déclencheur reste.

À **100 %**, les obligations ont leur déclencheur dans le KERNEL. **Aucune** n'est
seulement dans un module.

**Deux conditions de validité d'un déclencheur :**

1. Il se formule sur une **situation que l'agent SAIT reconnaître** (« je vais
   committer », « je change un statut », « le ticket a une checklist », « je touche à
   de la prod », « projet versionné »…). Une règle qui dépend d'une situation **non
   observable** par l'agent **doit rester tripwire complet** dans le KERNEL — pas de
   module possible.
2. La granularité des modules suit l'**ACTIVITÉ de l'agent** (ses verbes), pas le
   thème : une action résout vers **un seul** fichier (co-localiser les règles d'une
   même action). Couplé au **préchargement par rôle**, le chemin courant résout vers
   des fichiers **déjà ouverts** → ~zéro ouverture marginale ; le KERNEL n'attrape
   plus que les cas **rares hors-activité**.

C'est une optimisation **fine mais impérative** : minimiser le nombre de fichiers
ouverts **sans** jamais rater une obligation.

---

## 5. Principe 3 — chaque règle exécutable nomme son outil

Corollaire de l'« outillage obligatoire » de NORMS (toute opération sur l'état des
tâches/branches/repos/Redmine passe par un outil dédié, jamais à la main) :

- Une règle de module qui **s'exécute** doit **nommer le skill/script** qui la réalise.
- `pm-norms-doctor` vérifie que **tout skill/script cité existe** (`skills/`,
  `scripts/`). Une règle qui dit « fais X » **sans** outil, ou pointant un outil
  **absent**, est un **trou d'outillage** → à loguer (ticket type RM1923).
- Ainsi le doctor **fait remonter automatiquement les gaps** : NORMS et son outillage
  ne peuvent plus diverger en silence.

---

## 6. Critère d'admission au KERNEL

| Mettre dans le KERNEL | Mettre dans un module |
|---|---|
| Tripwire : **dangereux si raté silencieusement** ET court | Le **détail** d'une règle dont le déclencheur est dans le KERNEL |
| Le **déclencheur** (R) de **toute** autre obligation | Référence/lookup (tables d'ids, enums longs, exemples) |
| La colonne vertébrale d'onboarding (cascade, ownership, locking) | Procédures longues (MEP, bootstrap, sync config) |
| Règle dont la situation est **non observable** (pas de déclencheur fiable) | Tout ce qui ne sert qu'à une **activité** précise (→ chargé par le rôle) |

**Sort du runtime entièrement** (gouvernance, lu par humain seulement, jamais
injecté) : architecture de déploiement, versionning des normes, distribution des
skills cross-instance, configuration `.env`.

---

## 7. Convention de module (et sous-module)

Chaque module commence par un **en-tête « quand lire ceci »** explicite, qui reprend
mot pour mot le(s) déclencheur(s) du KERNEL qui y mènent :

```markdown
---
module: git-mep
triggers:                 # situations observables qui amènent ici (miroir du KERNEL)
  - "je crée une branche de travail pour un ticket"
  - "je livre / merge / mets en preprod"
loaded_by_roles: [worker-dev, worker-db, worker-infra]
tools: [mmi-pm-git-branch, pm-task-status-update]   # skills/scripts cités
---
# <Titre> — quand lire ceci : <résumé une ligne>
```

- **Beaucoup de modules** est attendu (pas de limite). Un domaine riche se découpe en
  **sous-modules** (`git/branch.md`, `git/mr.md`…), le KERNEL pointant vers la bonne
  granularité.
- **Une action = un fichier** : si une seule activité a besoin de plusieurs règles,
  elles **co-localisent**. Ne pas éparpiller une activité sur 3 fichiers.

---

## 8. Dédoublonnage — source unique + cross-ref, jamais recopie

Une information n'existe qu'à **un seul endroit canonique** ; ailleurs on **cross-ref**
(« cf. § X »), on ne **recopie pas**. Un paramètre canonique (taxonomie de `type`,
ids Redmine, mappings, enums) a une **source unique** ; ses consommateurs la **lisent
à l'exécution** plutôt que d'en dupliquer une copie figée.

---

## 9. Règle anti-périmé

**Ne jamais déclarer un outil manquant sans avoir vérifié `scripts/` / `skills/`.**
Plusieurs « trous » historiques de NORMS étaient **déjà bouchés** (l'outil existait,
la note était périmée). `pm-norms-doctor` attrape cette classe : tout outil cité est
contrôlé pour existence réelle.

---

## 10. Procédure : ajouter ou modifier une règle dans NORMS

1. **Recenser** : la règle est-elle une **obligation** (doit/jamais/obligatoire/
   systématique) ? Si oui elle DOIT être couverte par un déclencheur KERNEL.
2. **Classer** : tripwire complet (T, → KERNEL) ou détail différable (R, → module +
   ligne-déclencheur dans le KERNEL) ? Appliquer le critère §6.
3. **Placer** le contenu dans le bon module/sous-module (activité concernée, §7).
4. **Router** : ajouter/mettre à jour la ligne-déclencheur dans le KERNEL et l'en-tête
   `triggers:` du module (ils se **mirroir**).
5. **Outiller** : si la règle s'exécute, nommer le skill/script (`tools:`). S'il
   n'existe pas → loguer un trou d'outillage.
6. **Vérifier** : `pm-norms-doctor` (invariants §11) puis `pm-norms-assemble` + diff.
   - **Discipline ledger (obligatoire, non différable)** : si tu **reformules** ou
     **retires** une ligne qui existe dans l'oracle `_original-frozen.md`, le doctor la
     signale « non couverte ». Tu l'**inscris aussitôt** dans `dedup-ledger.yml`
     (`rewritten` avec `old:` = texte d'origine + `reason:`, ou `removed:` pour un
     doublon littéral) — **dans le même commit** que la reformulation. Ne jamais
     « laisser pour plus tard » : c'est ainsi que le ledger a dérivé de 8 versions
     (37 lignes non enregistrées, RM2070). La couverture est un **gate à tenir vert
     en continu**, pas une dette à réconcilier a posteriori. Avant d'inscrire, vérifie
     que c'est bien une reformulation (contenu conservé ailleurs) et **non une perte
     réelle** — sinon, restaure le contenu, ne l'enregistre pas.
7. **Versionner** : cf. §12.

---

## 11. `pm-norms-doctor.py` — invariants vérifiés

- **Non-perte texte** : `NORMS.md` assemblé == concaténation des sources (sinon échec).
- **Couverture comportementale** : **toute** obligation présente dans un module est
  atteignable depuis un **déclencheur du KERNEL** (zéro règle orpheline).
- **Routage valide** : tout déclencheur du KERNEL pointe vers un module **existant** ;
  tout module a son en-tête « quand lire ceci » + `triggers:` cohérents avec le KERNEL.
- **Outillage réel** : tout skill/script cité (`tools:`, corps) **existe** ; signale
  les trous (« fais X » sans outil).
- **Pas de doublon littéral** réintroduit ; cross-refs internes résolvent.
- **Pas de périmé** : aucune note ne déclare manquant un outil présent dans `scripts/`.
- **Budget de contexte** (RM1943) : aucun rôle ne dépasse son plafond
  `pm.config.yml :: context.budget_tokens` (délégué à `pm-context-budget.py
  --check`). Garde-fou anti-régression : tout module qu'on ajoute au
  **préchargement** d'un rôle (en-tête « Préchargé par : ») regonfle son contexte
  toujours-chargé — le doctor le refuse au-delà du plafond. Mesure et comparaison
  avant/après : `pm-context-budget.py --all-roles`.

---

## 12. Versionning de NORMS (anti-collision multi-sessions)

Inchangé par rapport à la procédure historique (plusieurs sessions partagent le même
filesystem et la même branche) : relire `schema_version` **sur disque** juste avant de
bumper ; `git fetch` + `pull --rebase` avant de committer ; le bump est la **dernière**
étape, suivie d'un **commit immédiat** ; conflits attendus sur `schema_version` /
`CHANGELOG` à résoudre délibérément.

**Où vit le numéro (RM2033)** : la version est portée par les **sources** —
`src/_frontmatter.txt` (`schema_version`) **et** le titre de `src/_full-body.md`
(`— vX.Y.Z`), qui doivent rester **cohérents** (le build échoue sinon). Donc, à
**chaque modification notable d'un module**, la procédure complète est :

1. éditer le(s) module(s) ;
2. **bumper** `schema_version` (frontmatter) **et** le titre (`_full-body.md`) ;
3. ajouter une entrée **`CHANGELOG.md`** (`## [X.Y.Z] - date`, format Keep a Changelog) ;
4. **réassembler** : `pm-norms-assemble.py build` → régénère `NORMS.md` **et**
   synchronise **`norms/VERSION`** (fichier ne contenant que le numéro, version de
   **NORMS seule**) ; `check` valide la cohérence des trois.

**Savoir si NORMS a bougé** : `norms/VERSION` est lisible en une commande, et
`scripts/pm-norms-changes.py` compile le delta entre deux versions :
`--check <connue>` (à jour ? exit 0/1), `--since <connue>` (entrées CHANGELOG à lire),
`--between A B`. Un agent compare sa version NORMS apprise à `norms/VERSION` et ne lit
que le delta (esprit KERNEL/modules-à-la-demande) au lieu de tout relire.

---

## Annexe A — Directives fondatrices (traçabilité)

Chaque directive donnée par le demandeur pendant la conception (RM1922), et où elle
est honorée — pour prouver qu'**aucune n'est perdue**.

| # | Directive (verbatim condensé) | Honorée en |
|---|---|---|
| D1 | NORMS trop lourd → factoriser, alléger, découper par rôles ; donner juste de quoi savoir qu'il faut aller lire plus / exécuter | §1, §2, couche C (addenda par rôle) |
| D2 | Machine d'états : la documenter en module ; KERNEL garde le principe + le skill/script qui transitionne et donne les statuts possibles | §4 (R) ; KERNEL = principe + `pm-task-status-update --list-next` (RM1923 #6) |
| D3 | `redmine-reference` = synchro de temps en temps → module séparé | module `redmine-reference.md` |
| D4 | Pas de limite au nombre de modules | §7 (beaucoup de modules + sous-modules) |
| D5 | Factoriser, dédoublonner, simplifier la lecture SANS perdre en compréhension | §3, §8 |
| D6 | Repérer où il manque un skill, à implémenter | §5 + RM1923 (le doctor fait remonter les gaps) |
| D7 | Pas un résumé qui perd une info ; **tout** est important | §3 (zéro perte, build+diff) |
| D8 | Un `pm-norms-doctor` pour vérifier NORMS comme on vient de travailler | §11 + RM1923 #7 |
| D9 | Consigner comment maintenir NORMS — « NORMS de NORMS » | **ce fichier** |
| D10 | Le KERNEL doit contenir TOUS les points d'entrée vers les modules, en minimisant le nombre de fichiers ouverts — optimisation fine mais impérative | §4 (index exhaustif + activité-centré + préchargement) |
| D11 | Consigner toutes mes directives (dans MAINTAINING) | **cette annexe** |
| D12 | Chaîne KERNEL → module/sous-module → skill → script ; le doctor unifie structure et outillage | §2, §5, §11 |

**Décisions d'arbitrage** (via questions) : ticket + plan d'abord (demandeur arbitre
le classement) ; trous d'outillage → ticket chapeau **RM1923** ; `NORMS.md` généré par
concaténation (source unique, non-perte prouvée par diff).
