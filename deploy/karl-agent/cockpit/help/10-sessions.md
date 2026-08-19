# Sessions & terminal

Une **session** = un agent (Claude Code, opencode…) qui tourne dans un `tmux`,
attaché à un ticket ou à un dossier de travail.

## Panneau « ▶ en cours »

Liste les sessions ouvertes. Les compteurs de l'en-tête indiquent : sessions
ouvertes · en **attention** (⚠ elles attendent une réponse) · au repos.

- **⚠ suivante ➜** : attache la prochaine session qui attend une réponse (cycle
  s'il y en a plusieurs).
- **✔ Oui** : répond « oui » à la session affichée. **✔ tout** : répond oui à
  toutes les sessions en attente d'un coup.
- **🔊 voix** : annonce à voix haute chaque session qui passe en attente et lit
  sa question (synthèse vocale du navigateur).

## Panneau « 🚀 sessions »

Gère des **jeux de sessions** enregistrés (un ensemble de sessions à relancer
ensemble) :

- **▶ Tout relancer** : ouvre d'un coup toutes les sessions du jeu.
- Une **tuile grise** = session enregistrée mais non démarrée : clic pour la
  relancer.
- Options par jeu : enregistrer, autostart, effacer.

## Terminal

La colonne de droite affiche le terminal de la session attachée (client maison
xterm.js). Il passe par un **WebSocket même origine** derrière le vhost HTTPS ;
un repli sur le port dédié `:7681` existe si le bundle xterm.js n'est pas chargé.
