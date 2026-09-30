# Santé du système PM (🩺 PM)

À côté de **🩺 poste**, qui surveille ta machine, le bouton **🩺 PM** surveille
le *système de gestion de projet lui-même* : ce qui est écrit, où, et si ça
arrive bien à destination.

Il porte un **compteur**. Ce chiffre n'est pas le nombre de choses à revoir un
jour : c'est le nombre de **soucis majeurs**, c'est-à-dire de situations où de
la donnée se perd ou s'est déjà perdue. Quand il n'y en a pas, rien ne
s'affiche — pas un zéro, pas une pastille grise. Un compteur qui montre quelque
chose tous les jours finit par ne plus être lu.

## Pourquoi ce bouton existe

Les champs personnalisés de Redmine s'activent **projet par projet**. Sur un
projet où un champ n'est pas activé, l'API accepte l'écriture, répond « succès »
et jette la valeur. Un ticket a ainsi porté **2 459 caractères d'étude**
invisibles côté Redmine pendant des semaines : le travail existait, il était
enregistré en local, et personne ne pouvait le voir sur la fiche web. Le
contrôle de configuration de l'époque répondait « aucun drift » — il ne
regardait pas cette question-là.

## Ce qui est surveillé

- **Champs Redmine** — pour chaque projet suivi, les champs dont l'outillage a
  besoin sont-ils activés ? Un manque ici veut dire : *tout ce qu'on y écrira
  sera jeté*.
- **Miroirs de champs** — y a-t-il, en local, du contenu rédigé (critères
  d'acceptation, actions de déploiement, branche, environnement de test) que
  Redmine n'a **pas pu** recevoir, faute de champ en face ? C'est la perte déjà
  advenue, chiffrée en caractères.
- **Cohérence des projets** — les manifestes se répondent-ils (`provided_by` ↔
  `used_by_clients`, `implements` ↔ `implemented_by`), la frontière `project/`
  vs `docs/` est-elle tenue, les dépôts déclarés pointent-ils une seule forge.
- **Normes** — les invariants de la structure NORMS : fraîcheur du document
  assemblé, index à jour, aucun marqueur de conflit resté dans une source.
- **Rapport** — l'âge du diagnostic lui-même (voir plus bas).

## Lire le détail

Clic sur **🩺 PM** : un onglet par famille, et la page s'ouvre d'office sur
celle qui va mal. Chaque ligne en défaut porte **la commande exacte** qui la
répare, avec un bouton *copier* — comme pour la santé du poste.

## La fraîcheur compte autant que le contenu

Le diagnostic n'est **pas** calculé quand tu ouvres la page : il interroge
l'API Redmine et balaie tout le parc de tâches, ce qui prendrait trop longtemps.
Il est produit en tâche de fond toutes les trois heures, et le cockpit lit le
dernier rapport en affichant **son âge**.

C'est délibéré, et c'est pourquoi un rapport trop vieux est lui-même compté :
avertissement passé six heures, **souci majeur** passé vingt-quatre. Un badge à
zéro parce que plus rien ne calcule ment davantage qu'il n'informe.

Pour forcer un calcul tout de suite — typiquement après avoir réparé quelque
chose :

```
python3 scripts/pm-health-report.py
```

`--check` affiche le diagnostic sans écrire le rapport ; `--only "Normes"` ne
joue qu'une famille.
