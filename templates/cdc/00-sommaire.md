# CDC <projet> — sommaire et méthode de travail

> **Statut** : rédaction en cours, en binôme. Document vivant.
> Ticket porteur : **RMXXXX**. Cadrage projet : [`overview`](../project/overview.md).

## Comment ce CDC est écrit

<Le demandeur> **pose les propositions** et **arbitre** ; l'agent **conseille**, signale les
conséquences et les pièges, puis **consigne**. Rien n'entre dans le CDC sans passer par le
registre : une proposition non tracée est une proposition qu'on croira avoir traitée.

| État | Sens |
|---|---|
| ✅ **validé** | arbitré par le demandeur — le reste du CDC doit s'y conformer |
| ❌ **invalidé** | écarté — gardé au registre **avec son motif**, pour ne pas le reproposer |
| 🟡 **proposé** | conseil rendu, en attente d'arbitrage — ne pas construire dessus |
| 🕐 **en attente** | posé, pas encore instruit |
| ⏸ **en réserve** | **arbitré, et volontairement écarté**, avec une **condition de reprise** nommée — la différence avec 🕐 est que la décision *a* été prise |

Convention : `D` = décision (proposée par le demandeur, sauf mention), `C` = conseil rendu par
l'agent, `Q` = question ouverte, `N` = note du vrac, `U` = retour d'utilisateur, `F` = fonctionnalité.
**Toujours trois chiffres** — `D050`, `Q012`, `C009`, `F001`, jamais `D50` : le tri lexical suit le tri
numérique, et les identifiants sont **stables**, jamais réattribués. Un amendement porte un suffixe
(`D009b`), il ne remplace pas.

## Le protocole

Sept temps — cadrer, regarder l'existant, balayer la surface, conseiller, arbitrer,
expliquer, vérifier — dont les quatre derniers tournent en boucle par lot. Détail dans
`grille-360.md` et dans la norme `modules/cdc.md`, dont ce modèle est le gabarit.

**Le cycle d'un lot** : éditer → régénérer (index, dictionnaire) → tester → commit → push sur
la branche d'intégration → MR → merge → déployer. Un arbitrage non livré est un arbitrage
qu'on croira livré.

## Pourquoi plusieurs fichiers, et pourquoi plats

`pm-wiki-sync` énumère `docs/*.md` en **non récursif** : le découpage se fait par fichiers
plats numérotés. Les sous-dossiers (`dict/`) sont des sources, pas des pages.

## Plan

| # | Chapitre | Objet | Avancement |
|---|---|---|---|
| 00 | ce fichier | méthode, états, plan | — |
| 01 | Périmètre | le problème, le non négociable, les suppositions | 🕐 |
| 02 → 1N | *thématiques* | un par sujet | 🕐 |
| 1N | Audit de l'existant | configurations, données, solutions comparables | 🕐 |
| 1N | Ce qu'on voudra observer | les mesures, décidées avant de construire | 🕐 |
| 1N | Comment ce projet meurt | risques et parades structurelles | 🕐 |
| 1N | Dictionnaire des données | **généré** depuis `dict/*.yml` | 🕐 |
| 90 | Registre des décisions | source de vérité des arbitrages | — |
| 91 | Vrac | notes verbatim et retours, tracés jusqu'à résolution | — |
| 92 | Glossaire | les mots, une fois | — |
| 99 | Questions ouvertes | ce qui n'est pas tranché, ce que ça bloque | — |

## Quand ce CDC est fini

Un CDC n'est pas fini quand on n'a plus d'idées : il est fini quand ces conditions sont
**vérifiables**, et le harnais les vérifie (`pm-cdc.py check`).

| Condition | Vérifiée par |
|---|---|
| aucune question d'urgence haute n'est ouverte | `99-questions-ouvertes` |
| aucune note du vrac n'est en suspens | `91-vrac`, chaque note tracée jusqu'à sa résolution |
| toute décision citée existe au registre, et réciproquement | le harnais |
| chaque fonctionnalité à jalon a un état et des dépendances renseignées | `dict/fonctionnalites.yml` |
| aucune fonctionnalité ne dépend d'un jalon ultérieur | le tri topologique |
| le premier jalon est chiffré, ticket par ticket | les `RM` portés par les `F…` |
| chaque décision structurante s'explique en langage d'utilisateur | l'aide, écrite pendant |

Ce qui reste ouvert après ça n'empêche pas de commencer : une question sans décision prise
*sous hypothèse* à son sujet ne bloque rien. Une question ouverte depuis longtemps sous
laquelle dix décisions ont été prises est bloquante de fait, quelle que soit son urgence
déclarée — c'est ce que compte le harnais.

## Du CDC aux tickets

Le CDC ne s'arrête pas au document : chaque fonctionnalité à jalon devient un **ticket
estimé** (`ticket:` dans `dict/fonctionnalites.yml`), dans l'**ordre de réalisation** calculé.
Un CDC qui ne débouche pas sur des tickets chiffrés n'a pas fini son travail — il a produit un
accord, pas un plan.
