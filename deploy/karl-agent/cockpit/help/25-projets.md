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

## Les icônes d'une ligne

Elles apparaissent à droite de la ligne et s'éclairent au survol. Un clic dessus
n'ouvre ni ne referme le client : il fait ce qu'il annonce, rien d'autre.

| Icône | Sur | Ce qu'elle ouvre au centre |
|---|---|---|
| 🏢 | un client | sa **fiche** : identité, statut, contacts, valeurs par défaut, projets, projets utilisés, docs |
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
