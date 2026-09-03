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

Chaque tuile porte **deux durées**, qui ne disent pas la même chose : le nombre
qui suit le titre est l'**âge** de la session (depuis son ouverture), et le
**⏳** le temps écoulé depuis sa **dernière sortie** — depuis quand elle n'a rien
produit. C'est la seconde qui décide d'un geste : ouverte depuis cinq heures et
active il y a trente secondes, une session n'appelle rien ; muette depuis
`2h14`, si. L'infobulle nomme les deux.

⏳ mesure le **dernier vrai message** de la conversation : une question, une
réponse, une action de l'agent. Ce que l'agent écrit tout seul n'y compte pas —
en particulier le récapitulatif `※ recap: …` que Claude Code affiche quand une
session reste sans réponse. Il écrivait au terminal sans que personne n'agisse,
et remettait le compteur à zéro : sur ce poste, onze sessions sur douze
paraissaient récentes alors qu'elles n'avaient rien produit depuis des heures —
jusqu'à deux jours pour certaines.

Un `~` après la durée (`⏳2h14~`) signale une mesure approchée : pour les moteurs
sans transcript exploitable, on retombe sur la dernière sortie du terminal. Une
durée approchée reste plus utile qu'un blanc.

## Panneau « 🚀 sessions »

Gère des **jeux de sessions** enregistrés (un ensemble de sessions à relancer
ensemble) :

- **▶ relancer (n)** : ouvre d'un coup les **n** sessions du jeu qui ne tournent
  pas. Il n'apparaît que dans la vue du jeu : en vue « sessions ouvertes » ou
  « tous les jeux », ce qui est affiché n'est pas le jeu, et le geste écrirait
  ailleurs que là où on regarde.
- Une **tuile grise** = session enregistrée mais non démarrée : clic pour la
  relancer. Son infobulle dit ce que le clic fera vraiment — *conversation
  mémorisée* (elle sera **reprise**) ou *conversation perdue* (le transcript a
  été purgé : une session **neuve** s'ouvrira dans le même dossier, sans le
  contexte d'avant). Dans la liste du jeu, la même distinction se lit
  🟡 reprenable / 🔴 perdue.
- Ce que les vues **ne montrent plus** : les sessions éteintes dont le **ticket
  est fermé** (le travail est fini, comme pour une session marquée ✅ terminé) et
  celles dont il ne reste **rien à rouvrir** (ni conversation, ni dossier
  mémorisé). Une session qui **tourne** reste toujours affichée, ticket fermé ou
  non. Pour retrouver une conversation ainsi masquée : carte
  **« Reprendre une session »**, qui liste les transcripts eux-mêmes.
- **＋ jeu** crée un jeu : critères laissés vides = jeu **manuel** (peuplé, si tu
  le veux, des sessions affichées) ; au moins un critère (client, projet, marque,
  tickets) = jeu **dérivé**, dont le contenu se calcule tout seul.
- **☑** passe en sélection, pour choisir les sessions une à une.
- **💾 → <jeu>** verse les sessions affichées dans le jeu nommé sur le bouton.
- Options par jeu : autostart, rétention d'affichage, effacer.

La carte **« Sessions enregistrées »** règle **n'importe quel jeu** : choisis-le
dans son propre sélecteur, en haut de la carte. Ce choix ne déplace **pas** le
jeu courant — celui qui gouverne le panneau « ▶ en cours » et qui reçoit « 💾 »
reste marqué **● courant** dans la liste. Tu peux donc renommer un jeu, changer
sa règle, sa rétention ou l'effacer sans quitter la vue sur laquelle tu
travailles. Le bouton **▶ relancer** de la carte vise le jeu affiché par la
carte ; celui du panneau de gauche vise le jeu courant.

La carte **« Reprendre une session »** filtre d'abord par **client**, et la liste
des projets se réduit aux siens (« tous » la rétablit). Client seul, sans projet :
toutes les sessions de ce client, tous projets confondus. Le contexte client du
bandeau pré-sélectionne le client sans figer le choix, et changer de client
n'y laisse jamais le projet d'un autre.

## Quand le moteur pose une question avant de démarrer

Un dossier que le moteur n'a jamais ouvert déclenche son garde-fou (claude :
« Is this a project you created or one you trust? »). Le lancement le signale
alors — « le moteur attend une approbation dans la session … » — et **n'envoie
pas** le prompt initial : la touche Entrée répondrait à SA question, pas à la
tienne (elle a déjà fait quitter des sessions à peine nées). Ouvre la session,
réponds « Yes, I trust this folder », puis renvoie ton instruction.

## Un ticket, une session à la fois

Lancer une session sur un ticket **déjà pris en charge** ailleurs — depuis la
fiche du ticket comme depuis le lanceur — affiche d'abord ce qui existe : quelle
session s'en occupe, son état, et à quel titre (ancrage, branche du registre,
worklog). Deux choix suivent : **rejoindre** cette session, ou **ouvrir quand
même** une seconde (avec ce que ça implique : même branche, même worktree, même
statut Redmine, et le second agent qui écrase les décisions du premier).

Ce qui ne déclenche rien : une session marquée **✅ terminé** (c'est ce que la
marque sert à dire), et l'absence de session. Une session **🔖 parké** ou
éteinte n'est pas « terminée » : elle est signalée.

## Terminal

La colonne de droite affiche le terminal de la session attachée (client maison
xterm.js). Il passe par un **WebSocket même origine** derrière le vhost HTTPS ;
un repli sur le port dédié `:7681` existe si le bundle xterm.js n'est pas chargé.
