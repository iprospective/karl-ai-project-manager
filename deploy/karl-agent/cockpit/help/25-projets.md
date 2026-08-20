# Projets — clients, projets et leurs fiches

Le panneau **📁 projets** liste tout ce que le PM connaît : les clients, et sous chacun
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

## La fiche, au centre

Elle donne la configuration utile (identifiant Redmine, dépôt GitLab, branche par
défaut), les **docs du projet** (cliquables — et de là, `⤢ au centre`), les
environnements déclarés avec leurs URL, les liens Redmine, les tickets **ouverts par
statut** et les derniers traités.

Comme toute vue centrale, elle devient un [onglet](onglets) : épingle-la pour la garder
sous la main pendant que tu travailles ailleurs.
