# Projets — clients, projets et leurs fiches

Le panneau **📁 clients/projets** liste tout ce que le PM connaît : les clients, et sous chacun
ses projets. Un clic sur un projet ouvre sa **fiche** dans le panneau central.

## Pourquoi ce panneau existe

La fiche projet existait déjà, mais on ne l'atteignait qu'en cliquant l'en-tête d'un
groupe de sessions **en cours**. Autrement dit : seulement pour un projet où une session
tournait à cet instant. Un projet au repos n'apparaissait nulle part, alors que sa fiche
était prête à être servie.

## Se déplacer dedans

- Un **clic sur un client** le déplie ou le replie. Le compte entre parenthèses dit
  combien de projets il porte.
- Le client du **contexte** (le sélecteur en haut de la colonne de gauche) est déplié
  d'emblée et porte la pastille `ctx` — les autres restent repliés : vingt clients
  dépliés d'un coup ne se lisent pas.
- Le **filtre** porte sur le client *et* sur le projet. Chercher `infra` montre les
  `infra` de tous les clients ; chercher un nom de client ramène tous ses projets. Sous
  filtre, tout est déplié.
- Une pastille verte `n ▶` indique les **sessions en cours** du projet (une session
  enregistrée mais non démarrée n'y compte pas : elle ne tourne pas).

## Les icônes d'une ligne

Elles apparaissent à droite de la ligne et s'éclairent au survol. Un clic dessus
n'ouvre ni ne referme le client : il fait ce qu'il annonce, rien d'autre.

| Icône | Sur | Ce qu'elle ouvre au centre |
|---|---|---|
| 🏢 | un client | sa **fiche** : identité, statut, contacts, valeurs par défaut, projets, projets utilisés, docs |
| 👤 | *(en-tête du panneau)* | l'**annuaire de contacts** — voir plus bas |
| ⚙ | un client | sa **configuration** — le `meta.yml` intégral |
| ⚙ | un projet | la **configuration du projet** — `meta.yml` : identifiant Redmine, dépôt GitLab, branche par défaut, aspects, dépôts déclarés |

La conf s'affiche **telle qu'elle est écrite**, en lecture seule : la reformater
masquerait ce qu'on vient justement y vérifier. Pour la modifier, l'outillage PM
(`mmi-pm`) — jamais l'édition à la main.

La **fiche client** montre aussi les *projets utilisés* : des projets d'un autre
client partagés avec celui-ci. Cette relation ne se lisait jusqu'ici qu'en ouvrant
le YAML.

## La fiche, au centre

Elle donne la configuration utile (identifiant Redmine, dépôt GitLab, branche par
défaut), les **docs du projet** (cliquables — et de là, `⤢ au centre`), les
environnements déclarés avec leurs URL, les liens Redmine, les tickets **ouverts par
statut** et les derniers traités.

Comme toute vue centrale, elle devient un [onglet](onglets) : épingle-la pour la garder
sous la main pendant que tu travailles ailleurs.

## L'annuaire de contacts

L'annuaire s'ouvre au centre par le bouton **👤 annuaire** du menu du haut — à côté
de « commandes pm », « réglages » et « journal ». Le bouton **👤** de l'en-tête
« Projets » y mène aussi, quand on est déjà dans les clients.

**Une personne, une fiche.** Avant, un contact vivait dans le `meta.yml` de SON
client : une personne présente chez vingt clients s'écrivait vingt fois — et
divergeait vingt fois. On avait ainsi 31 contacts pour 21 clients dont
**19 lignes pour la même personne**, en deux orthographes.

La recherche porte sur le nom **et sur toutes les adresses** : c'est tout
l'intérêt. Un contact recopié chez un client n'en connaissait qu'une ; une
fiche les porte toutes, et « contact@… » comme « mathieu@… » ramènent la même
personne. Les accents sont ignorés — chercher `noe` trouve `Noé`. Ce que tu as
cherché reste dans le titre de l'onglet : le rouvrir rejoue la même recherche.

Cliquer une ligne ouvre la **fiche** : adresses, téléphones, note, et surtout
**ses rattachements** — chez quels clients elle intervient et à quel titre.
Chaque rattachement ramène à la fiche du client.

Dans la fiche d'un client, les contacts sont **résolus** : un rattachement
affiche l'identité de la personne et se clique pour ouvrir sa fiche. Deux
mentions à connaître :

- **interne** — la personne est des nôtres. C'est un fait de **personne**, pas
  de ligne : avant, la même personne était marquée interne chez 2 clients et
  externe chez 17, ce qui ne voulait rien dire. Le routage du courrier entrant
  s'en sert pour ne jamais prendre une de nos adresses pour un indice de client.
- **ref inconnue** — la ligne pointe une fiche qui n'existe pas. C'est une
  anomalie, pas un contact vide : le rôle reste vrai, la fiche est à recréer ou
  le rattachement à corriger (`pm-contact.py list`).

L'annuaire se **lit** ici et s'**écrit** en ligne de commande — `pm-contact.py`
en est le seul point d'écriture, comme `pm-client-contact.py` l'est pour les
rattachements.
