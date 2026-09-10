# Worklog & état de session

La colonne de droite, sous le terminal, recentre l'information sur la **session
attachée**, répartie en onglets (dont **infos** et **état**).

## Le tableau de bord de la session

Le worklog n'est pas une liste : c'est le **tableau de bord de la session en
cours**. Il répond à « où en est-on, et qu'est-ce qui attend quoi ? » sans
relire la conversation. Chaque zone répond à une question précise :

| Zone | La question à laquelle elle répond |
|---|---|
| 🔔 **notifications** | qu'est-ce qui s'est passé de notable, et reste-t-il à traiter ? |
| 🔀 **MR** (onglet) | qu'est-ce qui est écrit mais pas encore intégré, ni promu ? |
| ❓ **à trancher** | quelles questions des tickets de la session attendent un arbitrage ? |
| 📥 **demandes à traiter** | qu'est-ce qui a été demandé et n'a pas encore de ticket ? |
| **sous-onglets par statut** | que reste-t-il à faire, à tester, à mettre en production ? |
| 📄 **documents** | qu'est-ce que la session a produit ou consulté ? |
| 🌿 **branches** | sur quoi le code a-t-il bougé ? |

Ces zones ne se recouvrent pas. Une **demande** appelle une action — souvent
ouvrir un ticket ; une **question** appelle un **arbitrage** (et un ticket ne se
ferme pas tant qu'il en reste une ouverte) ; une **notification** raconte un
fait ; un **ticket** porte un statut. Ce qui est traité **sort** de la liste sans sortir du worklog : la trace
reste, le backlog s'allège.

## L'onglet MR

Un sous-onglet **🔀 MR** rassemble les merge requests de la session, groupées par
étape du cycle :

| Groupe | Ce qu'il attend |
|---|---|
| ⇥ **à merger dans l'intégration** | la MR du ticket est ouverte |
| ✓ **mergées — à promouvoir en production** | le travail est dans l'intégration ; la promotion se fait **par lot** (`dev → main`), pas MR par MR |
| ★ **promues en production** | plus rien à faire côté MR |

Le groupe du milieu est celui qu'on perdait de vue : avant, le worklog ne montrait
que les MR **ouvertes**, et une MR mergée dans l'intégration disparaissait de
l'écran alors que le travail n'était pas en production.

Chaque ligne donne le **ticket** (cliquable), le **dépôt**, la branche
`source → cible`, l'**état** sur la forge, l'**âge**, et le bouton **⇥ merger**
quand la MR est encore ouverte. Le compteur de l'onglet ne compte que ce qui
appelle un geste : les MR promues n'y figurent pas.

La branche d'intégration n'est pas supposée : elle vient de la configuration du
projet, donc un projet qui n'appelle pas la sienne `dev` est lu correctement.

## Worklog

Le worklog reflète l'avancement de la session : tickets ouverts et leur statut,
activité récente. Il répond à « où en est-on / il reste quoi à faire dans cette
session » sans rescanner tout le contexte.

- Le **statut est live** ; la **fraîcheur** est affichée, et une éventuelle
  **dérive** (l'état réel diverge du dernier point) est signalée.
- La pastille de statut d'un **ticket** est **cliquable** : elle ouvre les
  transitions posables depuis l'état courant, sans quitter le worklog ni ouvrir
  la fiche. Le détail du menu (transitions grisées, motif et note réclamés,
  garde-fous) est décrit dans l'aide « tickets ». Un chantier libre — une entrée
  qui n'est pas un `RM<id>` — n'a pas de workflow : sa pastille reste inerte.

Les tickets sont répartis en **sous-onglets par statut** : ⏳ reste à faire,
🚀 à mettre en prod, ⏸ en attente / bloqué, ✅ fait, et ❔ statut inconnu quand
un statut n'est pas reconnu. Un onglet n'apparaît que s'il a du contenu.

L'onglet **🚀 à mettre en prod** rassemble les tickets `a_mep` et `en_mep`. Ils
étaient auparavant comptés dans « reste à faire », ce qui était trompeur : le
développement y est terminé, ce qui reste est une mise en production — un geste
batché (plusieurs tickets montent ensemble), souvent porté par un autre acteur.
Le worklog Markdown de session (`mmi-pm session-status show`) a la même section,
au même endroit : les deux vues ne doivent pas raconter deux histoires.

Dans chaque statut, les tickets sont **groupés par client / projet**, avec le
compte de chaque groupe. Une session touche souvent deux chantiers : à plat, on
ne voyait plus à quoi on touchait. Le groupement est un rendu, pas un tri —
l'ordre des tickets dans un groupe reste celui de la session, et l'ordre des
groupes celui de leur première apparition ; « hors projet » ferme la marche.
Quand tout appartient au même projet, aucun en-tête n'apparaît : il coûterait une
ligne pour ne rien dire.

Chaque ticket qui a une **merge request** porte son état sur sa ligne :

| Badge | Ce que ça veut dire |
|---|---|
| `⇥ MR` (orange) | MR ouverte : elle reste à merger |
| `✓ dev` (vert) | mergée dans la branche d'intégration |
| `✓ prod` (vert) | une MR de ce ticket a été mergée en production |

Un ticket **sans MR** n'affiche rien. Le badge mène à la MR, et son infobulle
détaille chacune quand il y en a plusieurs (dépôts distincts, reprise après un
renvoi) — la ligne, elle, ne montre que l'étape la plus avancée.

`✓ dev` est l'état normal d'un ticket livré : la **promotion** en production se
fait par lot (`dev → main`) et n'appartient à aucun ticket en particulier. Ce
n'est donc pas une promotion oubliée — l'infobulle le rappelle.

## Agir sur plusieurs tickets à la fois

Cocher des tickets du worklog fait apparaître les actions **qui ont un sens pour
eux** — et elles seules. Le compteur d'un bouton annonce le nombre de tickets
**concernés**, pas le nombre de cochés : « ▶ traiter (3) » sur cinq sélectionnés
dit ce qui va réellement partir.

| Bouton | Apparaît quand un ticket coché est… |
|---|---|
| 🔍 **analyser** | à étudier / chiffrer (`nouveau`, `a_etudier_chiffrer`, étude en cours) |
| ▶ **traiter** | à faire, en cours, à corriger, ou en test agent |
| ✔ **à tester** | en cours ou à corriger — c'est une **livraison** (note + protocole) |
| ⇥ **merger dev / prod** | porteur d'une **MR ouverte** (sinon le bouton n'apparaît pas) |
| ✅ **fermer** | livré : en test, ou en attente de MEP |

L'**analyse** (étude + chiffrage : estimation, critères, ROI) existait déjà, mais
noyée dans « traiter » : impossible de la demander seule. Elle a maintenant son
bouton.

La **fermeture** en lot passe par `pm-task-status-update`, comme un verdict
individuel. Elle ne force rien : un ticket refusé (checklist non cochée, branche
non mergée) reste ouvert et t'est listé avec sa raison — ces cas demandent un
arbitrage, qui se prend depuis la fiche du ticket.

Chaque lot montre d'abord un **récapitulatif** : ce qui part, et ce qui est
écarté avec le motif. Rien ne part sans que ce tableau ait été lu.

### ⇱ nouvelle session — sortir les intrus

Une session est ancrée sur **un** projet ; le fil, lui, ramasse des tickets
d'ailleurs. Cocher ces tickets puis **⇱ nouvelle session** ouvre une session
neuve, ancrée sur **leur** projet, qui les prend en charge — avec la consigne de
« ▶ traiter », et la session courante retrouve son seul chantier.

Deux garde-fous : les tickets cochés doivent appartenir **au même projet** (sinon
la session n'a pas d'ancrage — les projets en présence te sont nommés), et un
ticket dont le projet n'est pas résolu **reste sur place**, signalé, sans retenir
les autres. Les tickets embarqués quittent la liste « tickets ouverts » : c'est la
nouvelle session qui les porte. Le worklog, lui, n'est pas réécrit — il raconte ce
que la session a fait, et elle l'a fait.

## État de la session

L'onglet état distingue les situations d'une session :

- **bloquée** (attend une réponse) vs **sans réponse** — signalées sur plusieurs
  canaux (couleur, icône, libellé) ;
- les **notifications** de session sont rendues avant le travail en cours.
