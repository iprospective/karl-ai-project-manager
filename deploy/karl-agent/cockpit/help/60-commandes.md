# Commandes & actions PM

Le panneau **⚙ commandes pm** expose la surface CLI du PM sous forme d'actions
en un clic (catalogue config-driven).

## Fonctionnement

Chaque action correspond à un script `pm-*.py`. Les paramètres sont saisis via
un petit formulaire (ticket, statut, note…) ; les champs vides sont omis. Les
actions marquées **mutantes** demandent confirmation.

Exemples : changer le statut d'un ticket, commenter, lier deux tickets, lancer
un rapport de consommation, créer un client/projet, gérer une **instance cockpit
de test** (create / teardown).

## Où les retrouver

- **Panneau ⚙ commandes pm** : le catalogue complet.
- **Chips contextuelles** : certaines actions apparaissent directement sur les
  cartes concernées (ex. dans la [file de test](tests)).

Le résultat d'une action s'affiche dans une fenêtre de sortie (stdout du script).
