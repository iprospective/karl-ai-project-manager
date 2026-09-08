# 1N — Ce qu'on voudra observer

Les mesures qu'on voudra lire **quand ça tournera**, décidées **avant** de construire — sinon
on instrumente après coup ce qui était facile à instrumenter, pas ce qui compte. Ce chapitre
est la source de la page d'état du produit et de ce qu'il expose à une supervision.

## Les questions auxquelles l'exploitant doit pouvoir répondre

| # | La question | La mesure qui y répond | Où elle se lit |
|---|---|---|---|
| O001 | « est-ce que ça prend du retard ? » | | |
| O002 | « est-ce que quelque chose s'est perdu ? » | | |
| O003 | « qu'est-ce qui a échoué, et depuis quand ? » | | |

## Ce qui doit crier, ce qui doit se taire

Le silence est une fonctionnalité : une alerte qui se déclenche une fois sur deux n'est plus
lue. Pour chaque mesure, dire si elle **alerte** (et à quel seuil, mesuré, pas supposé) ou si
elle se **consulte**.

| Mesure | Alerte / consultation | Seuil, et d'où vient le seuil |
|---|---|---|
| | | |

## Ce qu'on refuse de mesurer

<Ce qu'on pourrait compter et qu'on décide de ne pas compter — parce que c'est du contenu,
parce que c'est nominatif, parce que la mesure coûterait plus que ce qu'elle apprend.>
