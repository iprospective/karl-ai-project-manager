# Emails — de la boîte de karl au ticket

Le panneau **📧 emails** transforme le courrier reçu sur `karl@iprospective.fr` en
tickets, en quatre gestes séparés. **Rien n'est créé sans toi** : le système propose,
tu valides.

**⤢ au centre** (sur un email déplié) l'affiche dans un onglet du panneau
central : en-têtes et **corps entier**, là où la carte du panneau le borne à
quelques lignes. L'onglet s'épingle et se rouvre au rechargement — y compris
sur un email déjà traité (RM2759).

## Le parcours

1. **📥 Relever** — lit la boîte en IMAP et remplit la file. Les dossiers classés côté
   serveur (ex. `INBOX.Clients`) passent en premier, puis `INBOX` : un correspondant
   inconnu du carnet n'est classé nulle part, on ne veut pas le rater. Lecture seule —
   rien n'est supprimé, déplacé, ni marqué lu. Rejouable sans risque de doublon.
2. **🎯 Router** — propose pour chaque email un client et, quand c'est certain, un
   projet, avec une **confiance** et la **source** de la proposition. Si rien n'est sûr,
   l'email reste « à classer » : aucune devinette.
3. **✎ Rédiger** — propose titre, projet, priorité et description. Toujours rien de créé.
4. **✓ Créer le ticket** — ta validation. Les champs affichés sont **modifiables** avant
   de valider.

## Lire la file

Chaque ligne montre l'expéditeur, le sujet, la date, le dossier, les pièces jointes, et
la cible proposée. Un clic déplie l'email : corps du message, proposition, actions.

| Repère | Sens |
|---|---|
| `calyclay/dolibarr` | client **et** projet déterminés |
| `calyclay/?` | client sûr, **projet à choisir** (le client en a plusieurs) |
| `à classer` | aucune source fiable — à toi de dire qui c'est |
| `↩ RM2661` | l'email **répond à un fil** : il donnera une note, pas un ticket |
| `→ RM2710` | un ticket a déjà été créé depuis cet email |
| `⊘` | écarté, avec son motif |

## Les actions d'un email

- **✎ Rédiger** — (re)fait la proposition. La case **« corps entier »** en haut du
  panneau envoie tout le message au modèle : les propositions sont nettement plus
  précises, mais le contenu du mail sort du poste. Sans elle, seuls le sujet,
  l'expéditeur et les 500 premiers caractères partent.
- **✓ Créer le ticket** — crée avec les champs affichés (corrigés si besoin). La
  description gardera la trace de l'email : expéditeur, date, sujet, `Message-ID`.
- **↩ Note sur…** — l'email prolonge un ticket existant : une **note** y est posée au
  lieu d'ouvrir un doublon. Utile quand le client a réécrit l'objet et que le marqueur
  `[RM<id>]` a disparu.
- **🎯 Reclasser** — corrige le client/projet. **La correction est apprise** : le même
  expéditeur sera routé tout seul la prochaine fois. Si cette personne t'écrit sur
  plusieurs projets, corrige vers le **client seul**.
- **⊘ Écarter** — sort de la file avec un motif (accusé de réception, hors sujet, déjà
  traité). L'email ne sera pas reproposé.

La case **« traités »** ré-affiche les emails déjà créés ou écartés.

## Bon à savoir

- La file vit **hors du dépôt** (`~/.local/state/karl-agent/mail/`, accès propriétaire) :
  c'est du courrier client, il n'a rien à faire dans un historique git.
- Les notifications automatiques (GitLab, monitoring, listes de diffusion) sont écartées
  à la relève, ainsi que les dossiers de rangement.
- Marquer les messages « lus » n'est **pas** proposé ici : c'est une action sur une boîte
  de production, elle reste en ligne de commande.

Voir aussi : [Commandes & actions](commandes) pour les mêmes gestes en CLI.
