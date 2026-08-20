# Onglets du panneau central

Le panneau central affiche **une vue à la fois** : le tableau de bord, un terminal de
session, la fiche d'un ticket, une fiche projet, ou la création de ticket. Les onglets,
en haut, gardent sous la main celles que tu veux retrouver.

## 📊 tableau de bord — l'onglet permanent

Le premier onglet est **toujours là** : il rouvre le tableau de bord (« ce qui requiert
ton attention »). Il ne se ferme pas et ne se détache pas — c'est aussi le point de
retour quand tu fermes le dernier autre onglet.

## Épinglé ou pas — la règle

- Une vue que tu ouvres devient un onglet **temporaire** (en italique). Il n'y en a
  **qu'un seul** : la vue suivante prend sa place.
- **⇧ Épingler** le fige : il reste, et les temporaires défilent à côté.
- **✕** ferme l'onglet. L'onglet voisin prend le relais ; quand il n'y a plus rien
  d'autre, on retombe sur le tableau de bord.

C'est ce qui évite de recréer la barre d'onglets de sessions retirée parce qu'elle
devenait illisible dès trois projets : la liste de référence des sessions reste la
colonne de gauche, l'onglet est un **marque-page**, pas un annuaire.

## Ce qui survit au rechargement

Les onglets **épinglés** sont restaurés à l'ouverture de la page, et celui qui était
actif se rouvre — **sauf** une session : rattacher un terminal au démarrage monterait
une vue que tu n'as pas demandée.

## ＋ Créer un ticket

Le lien **＋ créer un ticket** (panneau 🎫 tickets) ouvre la création **en pleine page**,
dans un onglet. On y trouve ce que la carte repliée ne pouvait pas porter : description
confortable, et sous « Options » la passe agent-testeur, l'environnement cible,
l'estimation (temps humain, temps IA) et la difficulté.

La cible se choisit en deux temps : **un client**, puis **ses projets** en boutons
radio. Le client par défaut est celui du contexte client du cockpit (menu en
en-tête) ; en changer ne touche à rien d'autre du formulaire — la saisie en cours
reste.

Choisir le type **bugfix** fait apparaître un bloc **étapes de reproduction**, requis,
avec la reproductibilité (toujours / souvent / parfois / rarement / jamais). Ce n'est
pas une formalité : sans ces étapes le ticket était rejeté par la validation, et un
bug qu'on ne sait pas reproduire se rouvre trois fois. Le bloc disparaît sur les
autres types.

À la création, le ticket créé s'ouvre dans sa fiche — l'onglet de création se referme.

La carte **« Nouveau ticket (saisie éclair) »** du panneau gauche reste là pour noter
une idée en trois secondes.
