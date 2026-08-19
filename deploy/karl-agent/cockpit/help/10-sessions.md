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

- **▶ relancer (n)** : ouvre d'un coup les **n** sessions du jeu qui ne tournent
  pas. Il n'apparaît que dans la vue du jeu : en vue « sessions ouvertes » ou
  « tous les jeux », ce qui est affiché n'est pas le jeu, et le geste écrirait
  ailleurs que là où on regarde.
- Une **tuile grise** = session enregistrée mais non démarrée : clic pour la
  relancer.
- **＋ jeu** crée un jeu : critères laissés vides = jeu **manuel** (peuplé, si tu
  le veux, des sessions affichées) ; au moins un critère (client, projet, marque,
  tickets) = jeu **dérivé**, dont le contenu se calcule tout seul.
- **☑** passe en sélection, pour choisir les sessions une à une.
- **💾 → <jeu>** verse les sessions affichées dans le jeu nommé sur le bouton.
- Options par jeu : autostart, rétention d'affichage, effacer.

## Terminal

La colonne de droite affiche le terminal de la session attachée (client maison
xterm.js). Il passe par un **WebSocket même origine** derrière le vhost HTTPS ;
un repli sur le port dédié `:7681` existe si le bundle xterm.js n'est pas chargé.
