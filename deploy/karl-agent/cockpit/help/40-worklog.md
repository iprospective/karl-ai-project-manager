# Worklog & état de session

La colonne de droite, sous le terminal, recentre l'information sur la **session
attachée**, répartie en onglets (dont **infos** et **état**).

## Worklog

Le worklog reflète l'avancement de la session : tickets ouverts et leur statut,
activité récente. Il répond à « où en est-on / il reste quoi à faire dans cette
session » sans rescanner tout le contexte.

- Le **statut est live** ; la **fraîcheur** est affichée, et une éventuelle
  **dérive** (l'état réel diverge du dernier point) est signalée.

Dans chaque statut, les tickets sont **groupés par client / projet**, avec le
compte de chaque groupe. Une session touche souvent deux chantiers : à plat, on
ne voyait plus à quoi on touchait. Le groupement est un rendu, pas un tri —
l'ordre des tickets dans un groupe reste celui de la session, et l'ordre des
groupes celui de leur première apparition ; « hors projet » ferme la marche.
Quand tout appartient au même projet, aucun en-tête n'apparaît : il coûterait une
ligne pour ne rien dire.

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

## État de la session

L'onglet état distingue les situations d'une session :

- **bloquée** (attend une réponse) vs **sans réponse** — signalées sur plusieurs
  canaux (couleur, icône, libellé) ;
- les **notifications** de session sont rendues avant le travail en cours.
