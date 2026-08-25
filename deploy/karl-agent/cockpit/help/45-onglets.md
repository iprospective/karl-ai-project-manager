# Onglets du panneau central

Le panneau central affiche **une vue à la fois** : le tableau de bord, un terminal de
session, la fiche d'un ticket, une fiche projet, la création de ticket, un **fichier,
un dossier, un commit ou un email** (RM2759) — et, depuis RM2816, les **⚙ commandes
pm** et les **🔧 réglages**, appelés depuis le menu du haut. Les onglets, en haut,
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

## Revenir d'où l'on vient (historique)

Trois boutons dans l'en-tête du cockpit : **←**, **→** et **🕘 historique**.

Le cockpit retient l'ordre dans lequel tu as visité les vues. Ça change trois choses :

- **Fermer un onglet te ramène à la vue précédente**, celle d'où tu venais — et
  non plus à l'onglet voisin dans la barre. C'est ce qui rendait le retour
  imprévisible : la destination dépendait de la position dans la barre, donc de
  l'ordre où les vues avaient été ouvertes une fois pour toutes, jamais de ton
  parcours. Ouvrir la fiche d'un ticket depuis une session puis refermer l'onglet
  te ramène maintenant sur *cette* session.
- **← / →** remontent et redescendent le parcours, comme dans un navigateur. `→`
  reste disponible tant que tu n'as pas ouvert une nouvelle vue.
- **🕘 historique** liste les vues visitées, la plus récente en tête : un clic y
  retourne. Les vues fermées entre-temps y restent, grisées — les cacher ferait
  croire que tu n'y es jamais passé.

Une vue fermée n'est jamais rouverte par un retour : elle est **sautée**. Tu l'as
fermée, te la remettre sous les yeux défairait ton geste. Et si rien de valide ne
reste dans l'historique, la fermeture retombe sur l'ancien comportement (l'onglet
voisin) — jamais sur rien.

L'historique vit avec la page : il n'est pas sauvegardé d'une session à l'autre.

## Épinglé ou pas — la règle

- Une vue que tu ouvres devient un onglet **temporaire** (en italique). Il n'y en a
  **qu'un seul** : la vue suivante prend sa place.
- **⇧ Épingler** le fige : il reste, et les temporaires défilent à côté.
- **✕** ferme l'onglet. L'onglet voisin prend le relais ; quand il n'y a plus rien
  d'autre, on retombe sur le tableau de bord.

C'est ce qui évite de recréer la barre d'onglets de sessions retirée parce qu'elle
devenait illisible dès trois projets : la liste de référence des sessions reste la
colonne de gauche, l'onglet est un **marque-page**, pas un annuaire.

## 📌 dans les listes

Un objet **épinglé** en onglet porte la même 📌 partout où il apparaît : tuiles
de sessions, revues ouvertes, tickets ouverts, résultats de recherche, file
« à tester », worklog, et projets. Plus besoin de chercher dans la barre si
l'onglet existe : la liste le dit.

Un onglet simplement **ouvert** (temporaire, en italique) n'est pas marqué — il
disparaîtra à la vue suivante ; ce qu'on signale, c'est l'épingle. La marque
apparaît et disparaît **au clic**, sans attendre le rafraîchissement.

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
