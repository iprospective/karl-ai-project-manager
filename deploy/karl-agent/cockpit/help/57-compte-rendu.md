# Compte-rendu client — annoncer ce qui est parti en production

**✉ compte-rendu** (menu du haut) répond à une question simple : *qu'est-ce qui est
en ligne chez le client et qu'on ne lui a pas encore dit ?*

Un ticket entre dans cette file **tout seul**, au moment où il passe en `en_mep`,
si son projet a l'option de notification client (`notif_client_mep`). Il en sort
quand tu l'as **annoncé**, ou quand tu l'as **écarté**. Rien ne part sans toi.

## Le parcours

1. Le **badge** du bouton compte les évolutions livrées qui attendent d'être annoncées.
2. Le **clic** déroule un client par ligne, avec son reste à annoncer : `Calicote (5)`.
3. La **page du client** liste ses tickets, **groupés par projet** — mais les cases se
   cochent **en travers des projets** : un même compte-rendu peut couvrir le site et la
   synchro. Tout est coché à l'ouverture (le cas courant : annoncer ce qui vient de sortir).
4. L'**aperçu**, en bas, est l'email exact qui partira — il est composé par le serveur,
   pas reconstitué par la page : ce que tu relis est ce que le client recevra. Il s'affiche
   **rendu** (comme dans une boîte mail), dans un cadre isolé du reste du cockpit.
5. **✉ Envoyer** l'envoie aux contacts du client, puis marque les tickets `sent_at` /
   `sent_to` (à qui, pas seulement quand).
6. **Écarter** sort les tickets cochés de la file **sans aucun email** — tout n'a pas à
   être annoncé (un correctif interne, une remise en ordre).

Les deux gestes se font en **deux clics** : le premier arme (le bouton dit alors à qui
ça part, ou combien de tickets seront écartés), le second exécute. Un armement oublié
expire tout seul.

## Ce que l'email contient

L'email part en **HTML** (avec un repli texte pour les lecteurs qui l'exigent). C'est ce
qui rend le protocole de test lisible : ses **tableaux** sont de vrais tableaux, ses titres
et ses listes sont mis en forme, et les cases `[x]` / `[ ]` deviennent ✔ / ☐.

Un seul email pour N tickets, avec pour chacun : le numéro, le titre, son lien, les
**critères d'acceptation** (« ce qui change ») et, si l'option est active, le
**protocole de test** (« comment le vérifier »).

La case **protocoles de test** au-dessus de la liste l'inclut ou l'exclut pour cet
envoi ; ton choix est mémorisé dans ce navigateur. Le défaut vient du projet
(`notif_client_mep.protocole`, vrai par défaut).

Quand la sélection couvre plusieurs projets, le corps est **groupé par projet** ; sur
un seul projet, aucun intitulé d'organisation interne n'apparaît.

## Prévenir aussi le demandeur

Chaque ligne porte une case **« demandeur »** : cochée, la personne qui a demandé le ticket
reçoit **son propre email**, ne contenant **que ses tickets** — elle n'a pas à découvrir ce
qui a été livré pour les autres. La case **« prévenir les demandeurs »**, en haut, les coche
toutes d'un coup.

Le demandeur est résolu depuis l'annuaire à partir du `creator` du ticket. Si son nom est
introuvable, ou s'il correspond à **plusieurs** fiches, il n'est **pas** prévenu et
l'écran le dit : on n'écrit pas à quelqu'un dont on n'est pas sûr. Un demandeur déjà
destinataire du compte-rendu ne reçoit pas deux fois le même message.

## Se relire avant d'écrire au client

Le bloc **Test d'envoi**, sous les boutons, envoie **le même compte-rendu** à une adresse
que tu choisis : un contact de l'annuaire dans la liste déroulante, ou une adresse saisie
à la main (elle est mémorisée pour la prochaine fois). Le sujet est préfixé `[TEST]`.

Un test **n'écrit rien** : pas de `sent_at`, pas de `sent_to`, la file ne bouge pas. Tu
peux en envoyer autant que tu veux avant le vrai envoi. En ligne de commande :
`mmi-pm client-notify test calicote --rm 3025 --to moi@exemple.fr`.

La liste déroulante propose **tout l'annuaire**, pas seulement les contacts du client : elle
ne dépend donc pas des destinataires configurés sur le projet. C'est voulu — un intervenant
doit pouvoir se relire sur n'importe quel projet sans figurer parmi les destinataires réels
du compte-rendu.

## Quand ça ne part pas

| Ce que tu vois | Pourquoi |
|---|---|
| **Aucun destinataire résolu** | l'option `notif_client_mep` est inactive sur le projet, ou ses contacts n'ont pas d'email. `mmi-pm client-notify config <client/projet> --actif true --add-contact <ref>` |
| **⚠ ref inconnue** | un contact référencé n'existe pas dans l'annuaire — il est ignoré, jamais deviné |
| **(option inactive)** sur un projet | ses tickets sont dans la file mais sans destinataire ; tu peux les écarter |

## En ligne de commande

Le panneau et la CLI font **exactement le même geste** — même code, même email :

```
mmi-pm client-notify pending                      # la file, groupée par client
mmi-pm client-notify preview calicote --rm 3025   # l'aperçu, sans rien envoyer
mmi-pm client-notify send calicote --rm 3025 --yes
mmi-pm client-notify dismiss calicote --rm 3042 --yes
mmi-pm client-notify queue calicote --rm 3025 --yes   # (re)mettre en file
```

`queue` sert quand la file doit être reformée à la main : un envoi qui a échoué, une
annonce à refaire, une démonstration du panneau. Il refuse un ticket qui n'est pas en
`en_mep` (rien à annoncer s'il n'est pas en production) — `--force` passe outre et le trace.

Le périmètre s'écrit `client` (tous ses projets) ou `client/projet`.
