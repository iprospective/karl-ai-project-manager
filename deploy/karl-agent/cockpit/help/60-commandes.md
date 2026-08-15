# Commandes & actions PM

Le panneau **⚙ commandes pm** expose la surface CLI du PM sous forme d'actions
en un clic (catalogue config-driven).

## Fonctionnement

Chaque action correspond à un script `pm-*.py`. Les paramètres sont saisis via
un petit formulaire (ticket, statut, note…) ; les champs vides sont omis. Les
actions marquées **mutantes** demandent confirmation.

Exemples : changer le statut d'un ticket, commenter, lier deux tickets, lancer
un rapport de consommation, créer un client/projet, gérer une **instance cockpit
de test** (create / teardown).

## Catégorie « mail » — relever la boîte de karl

- **Relever les emails de karl** : lit la boîte en IMAP et alimente une **file de
  triage** locale (les dossiers classés côté serveur d'abord, puis `INBOX` — un
  correspondant inconnu du carnet n'est classé nulle part, on ne veut pas le rater).
  Lecture seule : rien n'est supprimé, déplacé, ni marqué lu.
- **File des emails à traiter** : affiche la file courante sans se connecter.

- **Router les emails (client / projet)** : pour chaque email de la file, propose un
  client et, quand c'est certain, un projet — avec une **confiance** et la **source**
  de la proposition (fil du ticket, table apprise, compte Redmine de l'expéditeur,
  contacts du client, indice dans l'adresse). Quand rien n'est sûr, l'email reste
  « à classer » : le système ne devine pas.
- **Corriger le client/projet d'un email** : ta correction fait autorité **et est
  apprise** — le même expéditeur sera routé tout seul la prochaine fois. L'option
  « apprendre tout le domaine » est refusée sur gmail, orange, free… (elle enverrait
  tout le courrier de ce fournisseur chez un seul client).
  Astuce : si l'expéditeur t'écrit sur **plusieurs projets**, corrige vers le
  **client seul** — le projet restera demandé mail par mail plutôt que figé.

Cette relève **ne crée aucun ticket** : elle prépare le travail de triage
(rédaction et création à la validation viennent ensuite). Un email dont le sujet
porte `[RM<id>]` est reconnu comme une **réponse** dans un fil existant.

Un email déjà traité (ou écarté) n'est jamais reproposé : la relève est
rejouable sans risque de doublon.

## Où les retrouver

- **Panneau ⚙ commandes pm** : le catalogue complet.
- **Chips contextuelles** : certaines actions apparaissent directement sur les
  cartes concernées (ex. dans la [file de test](tests)).

Le résultat d'une action s'affiche dans une fenêtre de sortie (stdout du script).
