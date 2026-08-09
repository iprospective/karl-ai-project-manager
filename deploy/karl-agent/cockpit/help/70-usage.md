# Usage — tokens & coût

Le cockpit expose la consommation (tokens et coût) des sessions et des tickets.

- **Par session** : ce que le PM enregistre au fil de l'eau (worklog / métriques).
- **Par ticket** : la fiche d'un ticket affiche ses métriques cumulées (tokens
  d'entrée/sortie, coût estimé, temps).
- **Rapport de consommation** : l'action *conso-report* (panneau ⚙ commandes pm)
  agrège par projet, client, type, statut ou période, avec un top N et une
  sortie JSON optionnelle.

Les tarifs proviennent de la table de prix du PM ; un écart détecté avec les
tarifs publics du fournisseur fait l'objet d'un ticket dédié. Les montants
d'API externes sont en cents USD (diviser par 100 pour les dollars).
