# CDC — Glossaire / vocabulaire de projet

> Ticket : **RM2675** (étude + chiffrage, soumis à validation).
> Relié : RM2043 (privsep : aspects-docs libres → `.mmi-pm/docs/`), RM2309 (rendu markdown au
> cockpit), RM2368 (budget de contexte `project_docs`), RM2579 / RM2612 (sous-onglets du panneau
> droit), RM2586 / RM2673 (explorateur de fichiers par projet), RM2256 (jeu d'essai CalyMix).
>
> **Statut : ÉTUDE — soumise à validation.** Les points marqués `❓ARBITRAGE` demandent une
> décision du demandeur avant développement.

## 1. Objet

Chaque projet accumule un vocabulaire métier — jargon client, acronymes, unités, noms de pièces —
dont la maîtrise conditionne toute intervention, pour un humain qui arrive comme pour un agent qui
reprend un ticket. Ce vocabulaire est aujourd'hui dispersé dans les CDC, les docs techniques et les
logs de tickets : il faut le reconstituer à chaque fois.

**Objectif** : un glossaire par projet, tenu comme un artefact de première classe — versionné,
consultable sans checkout, et disponible au contexte des agents.

## 2. Constat — l'essentiel de la plomberie existe déjà

C'est le résultat le plus important de cette étude, et il change le chiffrage : **la demande est
déjà servie aux trois quarts par des briques en place**. Il ne reste ni stockage, ni transport, ni
rendu à construire.

| Besoin | Déjà là ? | Brique |
|---|---|---|
| Emplacement versionné, éditable par Mathieu | **oui** | `{project}/docs/` — aspects-docs *libres*, group-writable (RM2043) |
| Vu depuis le repo de code sous `docs/` | **oui** | symlink `<workspace>/docs → .mmi-pm/docs` posé par `pm-project-new` |
| Consultable **sans checkout** | **oui** | `pm-wiki-sync` publie tout `docs/*.md` au wiki Redmine (fusion 3-way) |
| Exposé au cockpit | **oui** | `karl-agent.py :: _project_docs_entries()` → `/projects` renvoie `docs[]` |
| **Rendu** markdown (titres, listes, **tableaux**) | **oui** | `mdToHtml()` (RM2309) — le rendu de tableaux est en place |
| Navigation par projet dans le panneau droit | **oui** | 📁 **fichiers** → barre de projets → nœud « docs » (RM2586 / RM2659 / RM2673) |

**Conséquence : déposer un `docs/glossaire.md` aujourd'hui le rend déjà lisible et rendu dans le
cockpit, et publié au wiki Redmine.** Ce qui manque n'est pas le support, c'est **la convention, la
recherche, et l'injection au contexte des agents**.

Deux réserves relevées au passage :

- **`docs/INDEX.md` est un fantôme.** `agents/worker-common.md` § *Contexte à charger* prescrit de
  lire `docs/INDEX.md` (« 1 ligne par doc ») avant d'ouvrir un doc, et `pm-context-budget.py` s'y
  réfère aussi. **Aucun script ne le génère et aucun projet n'en possède.** La règle de cascade
  documentaire des workers est donc, en pratique, inapplicable. → §7 et §9.
- **Aucun projet actif n'a de dossier `docs/`** (seuls deux projets archivés en ont un). CalyMix,
  le jeu d'essai demandé, n'a ni `docs/` ni le symlink : `pm-docs-migrate` les crée (idempotent).

## 3. Les cinq points « À cadrer », tranchés

### 3.1 Emplacement canonique → `{project}/docs/glossaire.md`

Le ticket pose l'alternative « repo de code (`doc/glossaire.md`) **ou** dossier PM ». **L'alternative
est fausse : le dossier PM donne les deux.**

- Il **est** `docs/glossaire.md` vu depuis le repo de code, via le symlink que `pm-project-new` pose
  déjà (`<workspace>/docs → .mmi-pm/docs`). L'argument « ça suit le code et se relit en MR » est donc
  satisfait sans rien faire.
- Il est en plus **lisible sans checkout** (wiki Redmine + cockpit), ce que le repo de code ne donne
  pas.
- Il reste **hors du dépôt de code** : un glossaire n'a pas à faire tourner la CI ni à polluer les
  diffs de code, et il doit survivre aux projets **sans repo de code** (projets purement
  documentaires — cas explicitement géré par RM2673).

**Décision proposée : `{project}/docs/glossaire.md`, nom de fichier imposé** (c'est la clé sur
laquelle le cockpit et l'injection de contexte s'accrochent).

### 3.2 Format → tableau à 4 colonnes + frontmatter

```markdown
---
wiki_sync: true
title: Glossaire
---

# Glossaire — <projet>

| Terme | Définition | Contexte d'usage | Alias |
|---|---|---|---|
| odométrie | Mesure de l'avance par les encodeurs de roues. | Dérive lentement ; recalée par la vision (RM2264). | — |
| HFOV | Champ horizontal d'une optique, en degrés. | 24 mm équivalent ⇒ 74° ⇒ champ = 1,5 × distance. | *field of view* |
```

**Pourquoi un tableau et non des sections :** l'usage dominant est la **consultation ponctuelle**
(« c'est quoi une rampe ? »), pas la lecture suivie. Un tableau se balaye à l'œil, se filtre en une
ligne de JS, se `grep` sans parseur, et **`mdToHtml` le rend déjà**. Contrainte de convention :
**définition ≤ 2 lignes** ; au-delà, le terme mérite un doc et la colonne *Contexte* le référence.

`wiki_sync: true` est le défaut de `collect_aspects()` ; on l'écrit explicitement pour que le
comportement soit lisible dans le fichier.

`❓ARBITRAGE 1` — la colonne **Alias** sert la recherche (« field of view » trouve HFOV) et les
acronymes. Elle alourdit un peu la saisie. La garder ?

### 3.3 Alimentation → saisie humaine d'abord, proposition agent ensuite

Deux voies, dans cet ordre :

1. **Lot 1 — saisie assistée.** Un outil `pm-glossaire.py` (`add` / `list` / `rm`) : tripwire #1 —
   toute écriture sur une donnée PM passe par un script, jamais à la main. Il garantit le tri
   alphabétique, l'unicité du terme et le format du tableau.
2. **Lot 3 — proposition par l'agent.** En fin de ticket, l'agent propose les termes qu'il a dû
   apprendre pour travailler, **en attente de validation** (statut `proposé` porté par une colonne
   ou un second tableau « en attente »). Jamais d'écriture directe : un glossaire qui se remplit
   tout seul devient un dépotoir, et sa valeur tient à sa **densité**.

`❓ARBITRAGE 2` — la proposition automatique en fin de ticket est-elle souhaitée, ou préfère-t-on
rester en saisie manuelle pure ?

### 3.4 Rendu cockpit → sous-onglet « vocabulaire » avec filtre

Le ticket demande une entrée « projets » → sous-onglet « vocabulaire » dans le panneau droit.

**Constat de cadrage : il n'y a pas d'onglet « projets » dans le panneau droit.** Les onglets sont
`worklog · infos · tickets · fichiers · git · conversation`. Le panneau qui joue ce rôle est
**📁 fichiers**, déjà organisé par projet (barre de projets, nœud « docs »).

Deux implantations possibles :

| | A — sous-onglet dans 📁 fichiers | B — nouvel onglet 📖 vocabulaire |
|---|---|---|
| Cohérence | le vocabulaire est *un document du projet* : il est à sa place | un 7ᵉ onglet dans une barre déjà chargée |
| Coût | faible (la barre de sous-onglets existe, RM2579/RM2612) | moyen (onglet + état + persistance) |
| Découvrabilité | moyenne (il faut ouvrir « fichiers ») | forte |

**Recommandation : A.** La barre d'onglets du panneau droit est déjà à six entrées ; en ajouter une
septième pour un document se paie en encombrement permanent contre un gain d'un clic. Le sous-onglet
se place à côté de « docs » dans le groupe du projet courant.

Fonctionnellement, au-delà du simple rendu déjà acquis : **un champ de filtre** qui masque les
lignes ne contenant pas la chaîne saisie (terme, définition ou alias). C'est la seule vraie
valeur ajoutée par rapport à l'ouverture du fichier — et elle est bon marché (filtre côté client sur
un tableau déjà en DOM).

`❓ARBITRAGE 3` — A (sous-onglet dans « fichiers ») ou B (onglet dédié) ?

### 3.5 Injection au contexte des agents → oui, mais plafonnée

C'est le point qui décide si ce chantier a de la valeur au-delà du confort de lecture.

**Oui, il faut l'injecter.** Un glossaire est par définition « ce qu'il faut savoir pour comprendre
le projet » : le laisser en consultation à la demande, c'est compter sur l'agent pour savoir qu'il
ne sait pas. Un agent qui lit « rampe » sans savoir que c'est la barre porte-guillotines ne va pas
ouvrir le glossaire — il va supposer, et se tromper silencieusement.

**Mais plafonnée**, sans quoi elle mange le budget de contexte :

- injection dans l'onboarding worker (`agents/worker-common.md`, cascade niveau 5), **avant** la
  lecture des docs à la demande ;
- **plafond dur : 1 500 tokens** (≈ 60 à 80 termes en format court). Au-delà, l'outil tronque et
  **le signale** (`… +N termes, cf. docs/glossaire.md`) — jamais de troncature muette ;
- le plafond se déduit du budget existant `context.budget_tokens.project_docs: 20000` : 1 500 = 7,5 %,
  vérifiable par `pm-context-budget --check`.

`❓ARBITRAGE 4` — 1 500 tokens est-il le bon plafond ? (≈ 70 termes ; au-delà, un glossaire de projet
cesse d'être un glossaire.)

## 4. Lots & chiffrage

Chiffrage en **temps agent** ; le temps humain est celui de la validation et de la saisie des termes.

| Lot | Contenu | Difficulté | IA | Humain |
|---|---|---|---|---|
| **1. Convention + amorçage** | template `glossaire.md`, doc de convention, `pm-docs-migrate` sur les projets actifs, glossaire CalyMix amorcé (4 termes du jeu d'essai) | low | 45 min | 20 min |
| **2. Outil `pm-glossaire.py`** | `add` / `list` / `rm`, tri, unicité, garde-fou de format, tests | medium | 1 h 15 | 10 min |
| **3. Sous-onglet cockpit + filtre** | sous-onglet « vocabulaire » dans 📁 fichiers, filtre client, tests `test_cockpit.js` | medium | 1 h 30 | 15 min |
| **4. Injection au contexte worker** | `worker-common.md` niveau 5, plafond 1 500 tokens + troncature signalée, `pm-context-budget` | medium | 1 h | 10 min |
| **5. Proposition agent** (optionnel, cf. ❓2) | tableau « en attente », proposition en fin de ticket, validation | medium | 1 h 15 | 15 min |

**Total lots 1-4 : ≈ 4 h 30 IA + 55 min humain.** Avec le lot 5 : ≈ 5 h 45 IA + 1 h 10 humain.

**Chemin minimal utile — lots 1 + 4 (≈ 1 h 45 IA).** Ils suffisent à capter l'essentiel de la
valeur : le glossaire existe, il est versionné, publié au wiki, **déjà lisible et rendu dans le
cockpit sans une ligne de code**, et surtout **il arrive au contexte des agents**. Les lots 2 et 3
sont du confort d'usage — réels, mais second.

> Réserve de chiffrage : les lots 3 et 5 touchent `index.html` (8 994 lignes) et
> `karl-agent.py` (9 578 lignes). Le chiffrage suppose de suivre les motifs existants
> (sous-onglets RM2579/RM2612, `_project_docs_entries`) sans refactorisation.

## 5. Jeu d'essai — CalyMix

Les quatre termes demandés au ticket, tels qu'ils seraient portés au glossaire :

| Terme | Définition | Contexte d'usage | Alias |
|---|---|---|---|
| **odométrie** | Mesure de l'avance de la machine par les encodeurs de roues. | Rapide mais **dérivante** ; recalée par la vision (RM2264 §3.3). Une erreur d'odométrie se lit comme une fausse dérive sur un rampant de pignon — c'est le couplage x↔y. | — |
| **rampe** | Barre transversale portant la rangée de guillotines. | 75 vannes × 40 mm = 3,0 m ; ~100 vannes ≈ 4,0 m avec la rallonge centrale. Sa largeur borne la marge de recalage latéral (RT-03). | rangée de vannes |
| **HFOV** | Champ horizontal d'une optique, en degrés. | 24 mm équivalent plein format ⇒ 74° ⇒ largeur de champ = **1,5 × la distance**. 16 mm ⇒ 97° ⇒ 2,25 ×. Dimensionne le nombre de caméras. | *horizontal field of view* |
| **métrologie** | Mesure dimensionnelle **juste**, par opposition à une simple détection. | Distingue les caméras latérales (métrologie, visée quasi-verticale) de la centrale (contexte, pas de métrologie) — RM2264 §3.2. | — |

Ce jeu d'essai vaut aussi **contrôle de la convention** : les quatre définitions tiennent en deux
lignes, la colonne *Contexte* porte le lien vers le doc qui approfondit, et les alias servent la
recherche.

## 6. Ce que cette étude ne tranche pas

- **Glossaire de client vs de projet.** La cascade PM est client → projet → tâche ; un terme comme
  « préfa horizontale » vaut pour tout CalyClay, pas seulement CalyMix. Le mécanisme d'héritage
  existe déjà pour les aspects (`{entity_client_dir}` puis `{project_dir}`) et s'appliquerait sans
  effort à `glossaire.md`. **Non chiffré ici** : à ouvrir si le besoin se confirme sur un 2ᵉ projet.
- **Multilingue / termes clients étrangers.** Hors périmètre.
- **`docs/INDEX.md`.** Le fantôme relevé au §2 dépasse ce ticket (il concerne toute la cascade
  documentaire des workers). → ticket séparé recommandé.

## 7. Décisions attendues du demandeur

1. `❓ARBITRAGE 1` — garder la colonne **Alias** ?
2. `❓ARBITRAGE 2` — activer la **proposition de termes par l'agent** (lot 5) ou rester en saisie manuelle ?
3. `❓ARBITRAGE 3` — sous-onglet dans **📁 fichiers** (recommandé) ou **onglet dédié** ?
4. `❓ARBITRAGE 4` — plafond d'injection au contexte agent : **1 500 tokens** ?
5. **Périmètre à engager** : chemin minimal (lots 1 + 4, ≈ 1 h 45 IA) ou complet (lots 1-4, ≈ 4 h 30) ?
