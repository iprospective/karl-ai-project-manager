# Fil de notifications

Le bouton 🔔 de l'en-tête ouvre le **fil** : ce qui demande ton attention, toutes sources confondues.
Il ne compte que quand quelque chose attend — sinon il ne dit rien.

## Une file, pas un journal

Le [journal](journal) est une **trace** : on y cherche après coup, il ne se lit pas en entier. Le fil est
une **file** : chaque entrée attend d'être lue, puis traitée, et sort alors de la vue. Ce sont deux
outils différents, et c'est voulu.

Une entrée porte son **origine** (l'ordonnanceur, une session, un agent, la forge, le mail, le système),
son **niveau**, son horodatage, et son état : ● neuve, ○ lue, ✓ traitée.

Deux gestes, et c'est tout :

- **○ lue** — vue, mais pas réglée : elle reste dans la file ;
- **✓ traitée** — réglée : elle quitte la vue. Le fil la garde ; l'onglet « tout, y compris traité » la
  retrouve. **✓ tout** marque d'un coup ce qui attend, et dit combien avant de le faire.

## Ce qui ne se répète pas

Une notification est identifiée par son **contenu**. Un travail qui échoue toutes les heures ne produit
donc pas vingt-quatre lignes : c'est la même, qui remonte avec son compteur (`×4`). C'est pour ça qu'on
peut laisser le fil ouvert sans le noyer.

## À qui ça s'adresse

Une notification peut viser **quelqu'un** — son nom est affiché à la suite du message. Quand elle est
**privée** (🔒), elle n'apparaît que dans la vue de cette personne : personne d'autre ne la voit ni ne
peut la marquer. Le filtre du haut permet de ne regarder que ce qui **concerne** une personne : ses
entrées, plus celles qui s'adressent à l'instance entière.

Le fil est lu au nom de l'utilisateur connecté, et la page le dit. Sans personne d'authentifiée — cockpit
derrière un simple secret partagé — aucune entrée privée n'est rendue : le propriétaire de l'instance se
déclare alors explicitement (`PM_NOTIFY_OWNER`), il ne se devine pas.

## En dehors du cockpit

- `mmi-pm notify` — le même fil en ligne de commande (`--done <id>` pour traiter) ;
- **par mail** — un message unique regroupe ce qui attend au niveau « avertissement » et au-dessus. Ce
  qui est déjà parti ne repart pas ; une alerte qui **s'aggrave**, si. Le destinataire se déclare dans
  `PM_NOTIFY_MAIL_TO` ; sans lui, rien n'est envoyé et rien n'est perdu.
