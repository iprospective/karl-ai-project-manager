# Aide du cockpit

Le **cockpit karl-agent** supervise les sessions d'agents IA, pilote le système
de gestion de projet (PM) et porte la console de test/revue des tickets livrés.

## Se repérer

La colonne de gauche a un onglet par surface :

| Onglet | À quoi ça sert | Aide |
|---|---|---|
| ▶ **en cours** | sessions ouvertes, celles qui attendent une réponse | [Sessions & terminal](sessions) |
| 🎫 **tickets** | rechercher/ouvrir un ticket, lien Redmine | [Tickets](tickets) |
| 📁 **projets** | tous les clients et leurs projets, fiche au centre | [Projets](projets) |
| 🚀 **sessions** | jeux de sessions enregistrés (relancer, autostart) | [Sessions & terminal](sessions) |
| 🧪 **à tester** | file de test/revue des tickets livrés | [À tester & revue](tests) |
| 📧 **emails** | courrier de karl → tickets (relève, routage, rédaction) | [Emails](emails) |

Deux surfaces ne sont **pas** dans cette colonne — on y va pour faire un geste, pas
pour surveiller du travail. Elles vivent dans le **menu du haut** et s'ouvrent au
centre, en [onglet](onglets) :

| Menu du haut | À quoi ça sert | Aide |
|---|---|---|
| ⚙ **commandes pm** | catalogue des actions PM en un clic | [Commandes & actions](commandes) |
| 🔧 **réglages** | thème, appareils, dictée, plafond mémoire, conf PM | [Réglages](reglages) |
| 🧩 **modules** (dans les réglages) | ce que l'instance porte, ce qui dépend de quoi, et ce qu'elle porte encore sans module | [Modules](modules) |
| 📜 **journal** | ce que le serveur et le navigateur ont consigné (sévérité, catégorie) | [Journal](journal) |
| 🔔 **fil** | ce qui demande ton attention, toutes sources confondues — une file qui se vide | [Fil de notifications](fil) |
| 📋 **CDC** | le cahier des charges vivant du projet en contexte : onglets fonctionnalités · CDC · feuille de route (modèle POC AtomBox) | [CDC vivant](cdc) |
| ✉ **compte-rendu** | ce qui est parti en production et n'a pas encore été annoncé au client : cocher, relire l'email, envoyer | [Compte-rendu client](compte-rendu) |

Le panneau **central** garde tes vues en [onglets](onglets) : une vue ouverte est un
onglet temporaire, épingle-la pour la conserver.

La colonne de droite affiche la session attachée : terminal, worklog, état.

- **◨** la replie et la déplie. Un repli fait à la main **tient** : attacher une
  session ne le défait plus (c'est une ouverture automatique, elle respecte ton
  geste) ; ouvrir un ticket ou un fichier, si — tu as demandé à voir quelque
  chose de précis. Au rechargement de la page, c'est le réglage « colonne de
  droite au démarrage » (🔧 réglages) qui décide, pas le dernier état.
- La **poignée** du bord gauche règle sa largeur (240 à 900 px), et ta largeur
  s'applique à tous les onglets — l'onglet conversation ne prend ses 460 px par
  défaut que si tu n'as rien réglé. « Réinitialiser » rend ces défauts.

## Sur un téléphone

Sur un écran étroit (moins de 820 px), le cockpit montre **une colonne à la fois** et une
barre de navigation en bas : **▶ panneaux** (en cours, tickets, projets, sessions, à tester,
emails — le badge rouge compte les sessions qui attendent une réponse), **▣ centre** (onglets,
terminal, fiches) et **▤ session** (worklog, infos, tickets, fichiers, conversation de la
session attachée). Attacher une session, ouvrir un ticket ou un fichier bascule sur le centre ;
ouvrir un onglet de droite bascule sur la colonne de droite. Rien n'est différent des mêmes
panneaux au bureau : c'est la même page, disposée autrement. `?layout=mobile` dans l'adresse
force cette disposition sur un grand écran, `?layout=desktop` l'inverse.

## Les boutons d'aide

- **🔓 déverrouiller** (en-tête) n'apparaît que si le coffre de secrets ou l'agent
  SSH est fermé — voir [Verrous](verrous).
- **❓ aide** (en-tête) ouvre cette documentation.
- **📜 journal** (en-tête) ouvre le [journal](journal) ; son badge compte les
  avertissements et erreurs survenus depuis la dernière ouverture.
- Un **`?`** près d'un panneau ouvre directement la page qui le concerne.

## L'en-tête, de gauche à droite

La pastille de **santé** (agent joignable, nombre de sessions), les compteurs des
sessions (attention / choix / au travail), **←** **→** **🕘** pour naviguer entre les
[onglets](onglets), puis les boutons de menu (⚙ commandes pm, 🔧 réglages, 📜 journal,
❓ aide, 🔓 déverrouiller si besoin) et le **cadenas** de connexion.

Le **pied de page** affiche la version du cockpit (`cockpit v3.x.y`). Si le serveur
et la page ne sont pas à la même version — déploiement en cours, ou cache du
navigateur — un avertissement l'indique à côté : recharger avec **Ctrl+F5** (ou finir
le déploiement) le fait disparaître.

## Références cliquables

Partout où un texte du cockpit cite un ticket (`RM2889`), un chemin de fichier ou un
terme du glossaire, la référence est **cliquable** : le ticket ouvre sa fiche ℹ, le
fichier s'ouvre dans l'onglet 📂 fichiers de la session, le terme souligné en pointillé
ouvre sa définition. Le **titre** d'un ticket ouvre sa fiche, sa **pastille de statut**
ouvre le menu des transitions. Les liens externes (Redmine, GitLab) s'ouvrent dans un
nouvel onglet du navigateur.

Les pages d'aide sont des fichiers markdown versionnés dans le repo
(`deploy/karl-agent/cockpit/help/`), servis par karl-agent. Elles sont
maintenues **au fil des développements** (norme « Développement du PM »).
