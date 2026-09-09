> 📂 **Module `cdc` — quand lire ceci :** on attaque un **projet neuf** (ou une refonte de
> fond) et le travail commence par un **cahier des charges complet** — pas un ticket, pas une
> étude d'une page. Aussi : je reprends un CDC existant, j'y consigne un arbitrage, ou je
> veux savoir quand il est fini.
> **Outils :** `pm-cdc.py` (init · dict · index · check) · `pm-wiki-sync` · gabarits
> `templates/cdc/` · **Préchargé par :** —.

## La méthode du CDC complet

Éprouvée sur un projet réel (140 décisions, 124 fonctionnalités, un POC qui lit le CDC), puis
confrontée aux CDC des autres projets du parc. Ce qui suit est la **synthèse**, pas la
transposition d'un cas.

**Le principe qui commande tout le reste** : quand le langage et le SGBD sont statués, coder
doit être une **formalité** — tout est déjà décrit par son rôle. Un CDC qui laisse le
développeur inventer n'a pas fini son travail.

## Trois livrables qui avancent ensemble

Jamais l'un sans les autres, **à chaque lot** :

1. **Le CDC en chapitres numérotés** — `docs/cdc-<prefix>-NN-<sujet>.md`, plats (le wiki
   n'énumère pas récursivement), avec trois fichiers de pilotage :
   - `90-decisions` — le **registre** : chaque proposition, le conseil rendu, l'arbitrage,
     l'état. Une décision amendée **reste** avec son motif : c'est ce qui évite de la
     reproposer dans six mois ;
   - `99-questions-ouvertes` — ce qui n'est pas tranché, **ce que ça bloque**, l'urgence,
     l'avis de l'agent. Une question tranchée y reste, barrée, avec le lien vers la décision ;
   - `91-vrac` — les notes **verbatim** du demandeur et les retours d'utilisateurs, chacun
     tracé jusqu'à ce qui l'a traité.
2. **Un POC d'interface** — maquette sans serveur, données engendrées, harnais de tests, qui
   **lit** le CDC (la page CDC affiche le registre réel, pas une copie). Un service ou une
   bibliothèque remplacent le POC par un **prototype de contrat** (schéma, API, jeu d'essai).
3. **Un dictionnaire des données** en fichiers structurés — `dict/*.yml` : entités, champs
   (**types logiques, jamais SQL** tant que le SGBD n'est pas statué), relations, énumérations,
   workflows, actions, templates, composants, protocoles, normes, routes, fonctionnalités,
   jalons. Le chapitre « dictionnaire » du CDC en est **généré** ; le POC lit les mêmes
   fichiers. **Une seule saisie par arbitrage.**

## Les états, et les identifiants

| État | Sens |
|---|---|
| ✅ validé | arbitré — le reste du CDC doit s'y conformer |
| ❌ invalidé | écarté, gardé **avec son motif** |
| 🟡 proposé | conseil rendu, en attente d'arbitrage — ne pas construire dessus |
| 🕐 en attente | posé, pas encore instruit |
| ⏸ en réserve | **arbitré** et volontairement écarté, avec une **condition de reprise** nommée |

`D` décision · `C` conseil · `Q` question · `N` note du vrac · `U` retour d'utilisateur ·
`F` fonctionnalité · `S` supposition · `O` mesure à observer. Ce qui se range dans N, Q, D/C
et F — et ce qui ne s'y range pas — est défini une fois, dans `session-tooling` § « Les quatre
rubriques » (RM3062) : une note n'entre au vrac que si elle peut **changer quelque chose plus
tard** ; une D est ce que le demandeur demande, pose ou tranche, ticketé ou non ; une F est une
feature atomique qui donne lieu à un ticket, le complète, ou reste à faire. **Toujours trois chiffres**
(`D050`, jamais `D50`) : le tri lexical suit alors le tri numérique. Les identifiants sont
**stables**, jamais réattribués ; un amendement porte un suffixe (`D009b`), il ne remplace pas.

## Le protocole — sept temps

| Temps | L'humain | L'agent | Livrable |
|---|---|---|---|
| **1. Cadrer** | dit le problème, la contrainte, le non négociable | reformule en une page ; sépare ce qu'il **croit comprendre** de ce qu'il **suppose** | `01-perimetre`, suppositions marquées |
| **2. Regarder l'existant** | donne l'accès : données, configurations, outils | **mesure sans lire les contenus** ; lit les configurations réelles ; audite les solutions comparables | chapitres d'audit — **des chiffres, datés** |
| **3. Balayer la surface** | arbitre les axes retenus | déroule la **grille 360°** sous les **cinq postures**, une question par cellule, sans répondre | `99-questions` initial — long |
| **4. Conseiller** | pose et repose | pour chaque question : un avis argumenté, un chiffre si possible, les options en tableau | conseils `C` |
| **5. Arbitrer** | tranche | consigne **dans le même lot** : décision, chapitre, dictionnaire, POC, aide | `90-decisions`, `dict/`, maquette |
| **6. Expliquer** | relit comme un utilisateur | écrit l'aide, le glossaire, le guide ; **toute décision qui ne s'explique pas revient au temps 4** | aide, glossaire, guides |
| **7. Vérifier** | — | `pm-cdc.py check` | le CDC testé |

Les temps **4 → 7 tournent en boucle par lot**, pas en séquence. Le temps 2 se rejoue chaque
fois qu'une décision repose sur une supposition ; le temps 3 se rejoue à chaque jalon.

**Le cycle d'un lot** : éditer → régénérer (dictionnaire, index) → tester → commit → push →
MR → merge → déployer. **Un arbitrage non livré est un arbitrage qu'on croira livré.**

## La grille 360° et les cinq postures

Une liste **fermée** d'axes (données, acteurs et portées, flux, états et workflows, sécurité,
conformité, performance, interopérabilité, exploitation, extensibilité, ergonomie, économie,
phasage), parcourue sur chaque sujet. Chaque cellule produit soit une question, soit un
**« sans objet — parce que »** : le « sans objet » est une réponse, c'est lui qui distingue une
surface couverte d'une surface oubliée. Détail et questions génératrices dans le gabarit
`grille-360.md`.

Une grille dit **où** regarder ; les postures disent **comment** : l'attaquant, l'exploitant à
3 h du matin, le nouveau venu, l'archéologue dans six mois, le concurrent. Ce sont les
changements de point de vue qui trouvent, pas la question ouverte : « qu'est-ce que j'ai
oublié ? » produit moins, et moins précis, que la lecture d'une configuration de production.

**Partir aussi de ce qui échoue** : lister les façons dont le projet peut **mourir**, puis
remonter aux décisions qui l'empêchent (gabarit `1N-comment-ce-projet-meurt.md`). Un CDC sans
cette section n'a pas fini sa réflexion.

## Le harnais — le CDC se teste

`pm-cdc.py check` casse sur :

- une **décision citée** qui n'existe pas au registre, et une décision **rédigée mais absente
  du tableau de synthèse** (donc invisible de tout ce qui lit l'index) ;
- une **relation** ou une table de **champs** qui pointe une entité non déclarée ;
- un **cycle** de dépendances entre fonctionnalités, une dépendance vers une `F…` inconnue ;
- une fonctionnalité qui **dépend d'un jalon ultérieur** — c'est ce qui rend le phasage
  honnête : déplacer une `F…` vers un jalon plus tard fait apparaître **tout ce qui doit
  bouger avec elle**, ou le déplacement est refusé ;
- une `F…` **écartée** dont une autre dépend encore : écarter est une **suppression en
  cascade**, portée par le test plutôt que par un dialogue qu'on cliquerait sans lire ;
- un **jalon vide** ; un **état hors de l'échelle** ;
- un **domaine réel** dans le CDC (anonymisation) — les domaines d'exemple sont admis, et
  `dict/anonymat.yml` déclare ceux du projet.

Il **avertit** (sans casser) sur le vrac en suspens, les `depend_de` à `null`, les
identifiants à moins de trois chiffres. Les avertissements d'une même famille tiennent sur
**une ligne** : crier soixante fois, c'est ne plus être lu.

## Les livrables d'un CDC complet

| Livrable | Ce qu'il porte |
|---|---|
| Sommaire et méthode | les états, le plan, **le critère de fin** |
| Périmètre | le problème, le non négociable, **ce que l'agent suppose**, le **hors-périmètre motivé** |
| Chapitres thématiques | un par sujet, avec les décisions qu'il porte |
| **Audits de l'existant** | configurations et données **réelles**, solutions comparables — des chiffres, **avec leur date** |
| **Ce qu'on voudra observer** | les mesures décidées **avant** de construire, et ce qui alerte vs ce qui se consulte |
| **Comment ce projet meurt** | les risques et leurs parades **structurelles** |
| **Dictionnaire** | généré depuis `dict/*.yml` |
| **Registre des décisions** | tout, y compris les amendées avec leur motif |
| **Vrac** | verbatim et retours, tracés jusqu'à résolution |
| **Questions ouvertes** | ce que ça bloque, l'urgence, l'avis |
| Glossaire | les mots du produit, et le mot du schéma quand il diffère |
| Guide utilisateur / développeur | écrits **pendant** le CDC — l'explication est un test |
| POC | maquette qui lit le CDC ; harnais qui teste le CDC |

## Le CDC vivant du projet et la réflexion des tickets (RM3015)

Le CDC complet d'un projet neuf (ce module) et le **CDC vivant** d'un projet en marche partagent
les mêmes registres, aux noms génériques (`docs/cdc.md`, `cdc-questions.md`, `cdc-decisions.md`,
`cdc-features.md`, `cdc-notes.md`, `cdc-roadmap.md`, `cdc-help.md`). Les quatre premiers sont
**régénérés** par `pm-think-merge` depuis les `.think.md` des tickets (`session-tooling` §
« Consignation par ticket ») ; ce qui est hors marqueurs y survit. Un CDC **par ticket**
(`cdc-rm<id>-*.md`) reste la référence de son sujet et le `cdc.md` du projet y renvoie.

## Deux registres de fonctionnalités — ne pas les confondre

| | CDC **prospectif** (`pm-cdc.py`) | CDC **rétrospectif** (`pm-cdc-features.py`, RM3043) |
|---|---|---|
| Source | `dict/fonctionnalites.yml`, saisi à l'arbitrage | les **tickets** du projet |
| Échelle | à trancher → décidé → maquetté → codé → éprouvé | prévu → en cours → livré |
| Quand | un projet qu'on **va** construire | un projet **déjà** construit, dont on veut la carte |

C'est la même échelle vue à deux moments : « prévu » recouvre *à trancher* et *décidé*, « en
cours » recouvre *maquetté* et *codé*, « livré » vaut *éprouvé* ; `en pause` et `écarté` sont
communs. Un projet prospectif **devient** rétrospectif quand chaque `F…` porte son `ticket:`.

## Quand le CDC est-il fini

Pas « quand on n'a plus d'idées » : quand les conditions du § « Quand ce CDC est fini » du
sommaire sont **vérifiables**, et vérifiées par le harnais. Ce qui reste ouvert ensuite
n'empêche pas de commencer — sauf une question ouverte **sous laquelle des décisions ont été
prises par hypothèse** : celle-là est bloquante de fait, quelle que soit son urgence déclarée.

**Le CDC finit en tickets.** Chaque fonctionnalité à jalon devient un ticket estimé, dans
l'ordre de réalisation calculé (`ticket:` dans `dict/fonctionnalites.yml`). Un CDC qui ne
débouche pas sur des tickets chiffrés a produit un accord, pas un plan.

## Les règles, en une page

- **Conseiller avant de consigner.** Le demandeur propose et arbitre ; l'agent conseille,
  signale les pièges, puis consigne. Jamais l'inverse.
- **Vérifier le CDC avant d'affirmer un manque** — grep, pas mémoire.
- **Trancher sur un chiffre, pas sur une intuition.** Mesurer avant de dimensionner, mesurer
  **sans lire les contenus**, dater la mesure, dire quand un chiffre est une estimation.
- **Le silence est une fonctionnalité.** Ne pas proposer ce qui crie.
- **Anonymiser.** Aucun nom de client, d'adresse ou de domaine réel — le harnais le vérifie.
- **Une seule source par donnée.** Le reste est généré ou lu.
- **L'explication est un test.** Ce qui ne s'explique pas à un utilisateur revient en conseil.
- **Le POC prouve par l'absence.** Une fonction de sécurité se teste par ce qu'elle refuse
  d'afficher.
- **Chaque lot se livre.** Commit, MR, merge, déploiement — à chaque arbitrage.
- **Comparer ce qui survit au jalon suivant**, pas ce qu'il faut construire d'abord : une V0
  dont la logique diffère de la cible est une V0 qu'on réécrit.
- **La méthode compte ses trouvailles.** Un axe qui n'a rien trouvé sur trois projets se
  retire ; la méthode évolue comme le CDC, par registre, avec des motifs.

## Ouvrir un CDC

    pm-cdc.py init --prefix rm2881 --projet "<nom>"   # gabarits → docs/, renommés
    pm-cdc.py dict                                    # (re)génère le chapitre dictionnaire
    pm-cdc.py index --out <poc>/cdc-index.json        # le registre, pour le POC
    pm-cdc.py check                                   # avant chaque commit du CDC

Le CDC vit dans le dépôt de **données** du projet (`.mmi-pm/docs/`), pas dans le dépôt de code
— il est synchronisé au wiki par `pm-wiki-sync`. Les sources (`dict/`, grille, trame
d'entretien) vivent sous `docs/cdc-<prefix>/` : ce sont des sources, pas des pages.
