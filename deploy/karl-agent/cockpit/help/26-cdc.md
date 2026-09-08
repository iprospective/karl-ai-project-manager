# CDC vivant

Le bouton **📋 CDC** du menu du haut ouvre le **cahier des charges vivant** du projet : la
liste des **fonctionnalités** (une ligne par ticket, livré / en cours / prévu), le **registre
des décisions**, les **questions ouvertes** et le **vrac** (remarques verbatim à trier).

- Un seul projet porte un CDC → il s'ouvre directement sur son sommaire ; plusieurs → on choisit.
- Les liens entre chapitres naviguent dans la fenêtre ; **⇥ au centre** envoie le chapitre en onglet.
- Un projet porte un CDC dès qu'il a un `docs/cdc-<prefix>-00-sommaire.md` (modèle AtomBox) ;
  le chapitre des fonctionnalités est généré depuis ses tickets par `pm-cdc-features`.

Le CDC se tient à jour **au fil de l'eau**, comme NORMS : une décision, une question, une
fonctionnalité livrée entrent dans le registre dans la même livraison.
