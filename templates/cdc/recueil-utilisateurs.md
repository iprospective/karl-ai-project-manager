# Recueillir les besoins et les idées des utilisateurs

Un CDC écrit par un binôme n'a pas été écrit par ses utilisateurs. Ce document dit comment on
les fait entrer — sans les trois pièges classiques.

## Trois pièges, trois parades

| Piège | Ce qui se passe | Parade |
|---|---|---|
| **le questionnaire** | on obtient des réponses aux questions posées — jamais ce qu'on n'a pas pensé à demander | observer *ce qu'ils font*, pas ce qu'ils disent |
| **la liste de souhaits** | chacun demande la fonction qui lui manque ce matin ; un catalogue sans priorité | remonter du souhait au **problème** : « je voudrais X » → « qu'est-ce qui vous arrive sans X ? » |
| **l'utilisateur expert** | il décrit ses contournements comme des besoins | le contournement est un **symptôme** — chercher ce qu'il contourne |

## Trois natures, gardées distinctes

| Nature | Ce que c'est | Quand on le recueille |
|---|---|---|
| **fait** | observé : configuration, volume, geste répété, règle en place | d'abord — c'est ce qui ment le moins |
| **irritant** | ce qui coûte du temps, ce qu'on fait à la main, ce qui fait peur | ensuite |
| **idée** | ce que l'utilisateur voudrait | **en dernier** — sinon elles contaminent le reste |

## Trois canaux, du moins cher au plus riche

### 1. L'observation silencieuse

Configurations, arborescences, volumes, règles de tri, raccourcis — **sans lire les contenus**
(index, comptages côté serveur, agrégats). Reproductible en quelques secondes, sans déranger
personne. Produit un chapitre d'audit (`1N-audit-existant.md`).

### 2. L'entretien guidé — trente minutes, une trame

1. **« Racontez-moi hier matin. »** — un récit d'une séquence réelle, pas une opinion. On note
   les gestes, les outils ouverts, les allers-retours.
2. **« Qu'est-ce qui vous a fait perdre du temps cette semaine ? »**
3. **« Que faites-vous à la main que vous ne devriez pas avoir à faire ? »**
4. **« Qu'est-ce qui vous a fait peur, ou que vous n'osez pas toucher ? »**
5. **« Si vous aviez une baguette magique — une seule chose. »** — les idées, en dernier.

On ne montre **pas** la maquette pendant l'entretien : elle oriente les réponses.

### 3. La maquette instrumentée

Sur la maquette en ligne, un bouton **« ça, je ne comprends pas » / « ça me manque »** sur
n'importe quel élément. Il capture le **contexte** (page, élément, geste précédent) et un mot
de l'utilisateur. Des retours **situés**, pas abstraits — et les décisions qui ne s'expliquent
pas dans l'usage, celles que l'aide n'avait pas attrapées.

Mettre la maquette devant des personnes **qui ne sont pas le demandeur**, avant la première
version : c'est la première donnée utilisateur du projet, et le premier test de la méthode.

## Le circuit

```
retour (rôle, canal, nature) ──> 91-vrac (Uxx, 🕐)
                                    │
                    ┌───────────────┼────────────────┐
                    ▼               ▼                ▼
               question Qxx    décision Dxx     écarté, motif
                    └───────────────┴────────────────┘
                                    ▼
                          couverture : traités / écartés / en suspens
```

Le harnais vérifie qu'aucun retour n'est **en suspens** depuis plus de N lots. Une décision
qui cite « répond à quatre retours d'utilisateurs » a une force qu'un avis d'agent n'a pas.
