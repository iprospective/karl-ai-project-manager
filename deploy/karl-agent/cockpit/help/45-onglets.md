# Onglets du panneau central

Le panneau central affiche **une vue à la fois** : le tableau de bord, un terminal de
session, la fiche d'un ticket, une fiche projet, la création de ticket — et, depuis
RM2759, un **fichier, un dossier, un commit ou un email**. Les onglets, en haut,
gardent sous la main celles que tu veux retrouver.

## 📊 tableau de bord — l'onglet permanent

Le premier onglet est **toujours là** : il rouvre le tableau de bord (« ce qui requiert
ton attention »). Il ne se ferme pas et ne se détache pas — c'est aussi le point de
retour quand tu fermes le dernier autre onglet.

## ⤢ au centre — fichier, dossier, commit, email

Ces quatre contenus se lisaient déjà, mais à l'étroit : un CDC dans une fenêtre par-dessus
le reste, un patch dans la colonne de droite. Le bouton **⤢ au centre** les envoie dans un
onglet, avec la place qu'ils demandent — et de quoi y revenir.

| Où le trouver | Ce qui s'ouvre |
|---|---|
| Fenêtre d'un document (fiche projet → *Docs projet*) | 📄 le document, markdown rendu |
| Panneau 📁 fichiers, sur un fichier ouvert | 📄 le fichier (rendu si `.md`, brut sinon) |
| Panneau 📁 fichiers, au-dessus du fil d'Ariane | 🗂 le dossier, **navigable** au centre |
| Panneau ⎇ git, bouton ⤢ d'une ligne de commit | ⎇ le commit et son patch complet |
| Panneau 📧 emails, sur un email déplié | 📧 l'email, en-têtes et **corps entier** |

Rien ne change dans ces panneaux : le bouton s'ajoute, les clics existants font ce
qu'ils faisaient. Un commit passe par sa session (`/git/show`) : sans session attachée,
la ligne reste informative plutôt que d'offrir un clic qui échouerait.

Ces onglets s'épinglent comme les autres et **se rouvrent au rechargement** — leur clé
porte tout ce qu'il faut pour recharger le contenu. Si la source a disparu entre-temps
(session fermée, fichier déplacé, email traité), l'onglet **le dit** : un panneau vide
se lirait comme une panne du cockpit.

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
