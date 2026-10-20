---
type: knowledge
product: mail
created: 2026-10-20
---

# Migrer des boîtes mail IMAP d'un hébergement à l'autre

Tiré de la migration Calicote (RM3199, 20/10/2026) : 24 boîtes, 54 639 messages,
d'un hébergement tiers vers un conteneur du parc. Réussie sans perte — mais
chacun des pièges ci-dessous a été découvert **après** avoir mordu.

## Le piège central : une synchro additive ne réplique pas les suppressions

`imapsync` sans `--delete2` **ajoute** à la destination, il ne retire rien. Tout
message supprimé ou déplacé sur la source **après** avoir été copié reste en
place sur la destination, indéfiniment.

Chez Calicote, l'utilisatrice principale avait fait du ménage dans sa boîte les
jours précédant la bascule. Au moment de basculer : **59 180 messages côté
destination contre 31 161 côté source.** 28 000 messages ressuscités, qui
« revenaient » sous ses yeux dès que son client a pointé sur le nouveau serveur.

> **Tant que la source fait foi, la synchro doit être un miroir, pas un ajout.**
> `--delete2` ne devient interdit qu'**après** la bascule, quand la destination
> devient la référence.

Un mode par intention, avec une garde par sens, évite de se tromper :

```sh
case "$MODE" in
  miroir) ARGS+=( --delete2 --expunge2 --noexpunge1 ) ;;  # avant bascule : source = référence
  vidage) ARGS+=( --delete1 --expunge1 ) ;;               # après bascule : vider la source
  "")     ARGS+=( --noexpunge1 ) ;;                       # additif, rien n'est supprimé
esac
# la source n'est effaçable qu'en mode vidage, la destination qu'en mode miroir
[ "$MODE" != "vidage" ] && refuser --delete1 --expunge1 --delete1emptyfolders --move*
[ "$MODE" != "miroir" ] && refuser --delete2 --expunge2
```

## Le master user masque les mots de passe faux

Une synchro qui écrit via un master user (`<boîte>*imapsync`) **n'utilise jamais
le mot de passe de la boîte** côté destination. Elle réussit donc parfaitement
alors que l'utilisateur ne peut pas se connecter.

Chez Calicote, **9 boîtes sur 24** avaient un mot de passe divergent entre le
coffre et la base du nouveau serveur — ceux changés en cours de préparation. Rien
ne l'a signalé jusqu'à ce qu'une utilisatrice échoue à ouvrir son webmail.

**Tester explicitement, boîte par boîte, avant la bascule** :

```sh
doveadm auth test '<boîte>' '<mot de passe du coffre>'
```

Et attention au **schéma de hachage** : écrire un `{SHA512-CRYPT}` là où la base
utilise `{SHA512}` (PostfixAdmin en `php_crypt:SHA512`) rend les comptes
inutilisables avec un `internal auth failure` peu parlant. Calquer sur une entrée
existante, et retester juste après l'écriture.

## Les UIDVALIDITY ne survivent pas

`imapsync` recrée les messages : les UID et UIDVALIDITY de la destination n'ont
aucun rapport avec ceux de la source. Tout client IMAP invalide alors son cache
et **retélécharge intégralement** — c'est le protocole qui veut ça.

Sur une boîte de 29 Go, ce n'est pas un détail : plusieurs heures, et un risque
réel d'index corrompu avec certains clients (Apple Mail notamment).

Conseils à donner avant la tournée des postes :

- **modifier le compte**, ne pas le recréer : le retéléchargement a lieu dans les
  deux cas, mais on garde signatures, règles et dossiers locaux ;
- **passer les pièces jointes sur « aucune »** avant de changer le serveur, sur
  les grosses boîtes : l'essentiel du volume est là ;
- prévoir que ça tourne hors présence, en filaire.

## Le transport de transition, et l'ordre des opérations

Déclarer les domaines dans PostfixAdmin **avant** la bascule du MX fait que le
nouveau serveur les considère comme locaux et livre en LMTP — dans des boîtes que
personne ne lit encore. Chez Calicote : 11 messages détournés, dont 9 pour
l'utilisatrice principale.

Le remède est un `transport_maps` qui force le relais vers l'ancien serveur,
consulté **avant** `virtual_transport` :

```
calicote.com   smtp:[ancien-serveur]:25
```

Mais il devient un piège à son tour : une fois le MX basculé, le nouveau serveur
accepte le courrier et **le renvoie à l'ancien**, où plus personne ne lit. Les
utilisateurs ne voient plus rien arriver.

> **L'ordre qui évite les deux écueils** : vider le transport → vérifier qu'une
> livraison locale aboutit (`relay=…[private/dovecot-lmtp]`) → basculer le MX.
> Et non l'inverse.

## La fenêtre de divergence, et comment la fermer

Entre la reconfiguration des postes et la bascule du MX, les utilisateurs
écrivent sur la destination pendant que le courrier arrive encore sur la source.
Ce qui n'existe que sur la destination, ce sont **les envois et les brouillons** —
les messages reçus, eux, sont des copies.

Procédure qui a fonctionné :

1. inventorier par **Message-ID** ce qui est sur la destination et pas sur la source ;
2. remonter ces seuls messages (IMAP `APPEND`, en préservant `INTERNALDATE` et les drapeaux) ;
3. contrôler qu'il ne reste rien d'unique ;
4. miroir, puis vidage du transport.

Chez Calicote le delta tenait en **6 messages**. Mais il se reconstitue tant que
les utilisateurs écrivent : **faire arrêter l'usage le temps de l'opération**,
sinon on court après une cible mouvante.

Ce qui est perdu dans l'affaire, ce ne sont pas les messages mais les **actions** :
lu/non lu, classements et suppressions faits sur la destination avant le miroir.
À annoncer aux utilisateurs.

## Résidus de vidage : les accents décomposés

Après `--delete1`, 99 messages sont restés sur la source dans 7 boîtes, alors
qu'`imapsync` annonçait `0 messages found in host1 not in host2`.

La cause : les noms de dossiers. La source écrivait `TRE&AwE-SORS DE CORALIE`
(accent **décomposé** : E + U+0301) là où la destination avait
`TRÉSORS DE CORALIE` (**précomposé**). Pour imapsync ce sont deux dossiers
distincts : il ne reconnaît pas les messages comme déjà copiés et ne les supprime
donc pas.

Sans gravité — vérifier par Message-ID que chaque résidu existe bien à
destination avant de le supprimer à la main — mais à savoir pour ne pas croire
à une perte.

## Vérifier : faire confiance à imapsync, pas à ses propres comptages

Comparer des totaux obtenus par deux méthodes différentes (IMAP d'un côté,
`doveadm` de l'autre) produit des écarts qui n'existent pas : les deux ne
dénombrent pas les mêmes dossiers. Pendant cette migration, ces faux écarts ont
fait conclure trois fois à des pertes imaginaires.

La mesure qui fait foi est celle d'imapsync, qui compare message par message :

```
Messages found in host1 not in host2 : 0
Messages found in host2 not in host1 : 0
Detected 0 errors
```

Et pour trancher un doute, la comparaison par **Message-ID** est la seule fiable.

## Gotchas d'outillage rencontrés

- `doveadm search` renvoie **`mailbox-guid uid`**, pas un identifiant de message :
  `doveadm fetch … GUID <x>` échoue silencieusement. Utiliser
  `doveadm fetch -u <boîte> 'hdr.message-id' ALL SINCE <date>`.
- `ssh -n` et un heredoc sont **incompatibles** : `-n` ferme l'entrée standard,
  le heredoc n'arrive jamais et la commande échoue sans rien afficher. Dans une
  boucle `while read`, c'est l'inverse qu'il faut : sans `-n`, le `ssh` consomme
  l'entrée et la boucle ne traite qu'une seule ligne.
- Ne jamais laisser de fichier `.bak` dans un répertoire `conf.d` : il est chargé
  comme les autres, et un `50-user.bak-…` lu après `50-user` réimpose l'ancienne
  valeur sans que rien ne le signale.

## Checklist

- [ ] tester `doveadm auth test` sur **chaque** boîte avec le mot de passe du coffre
- [ ] vérifier les certificats servis par **dovecot ET postfix** (993, 143, 25, 587, 465)
- [ ] poser le hook `letsencrypt/renewal-hooks/deploy/` qui recharge dovecot et postfix
- [ ] vérifier `submission_relay_host` si dovecot occupe le 587
- [ ] créer les alias techniques (`*-www@`) pour que les avis de non-remise aient une boîte
- [ ] faire arrêter l'usage, puis : inventaire du delta → remontée → **miroir** → snapshot
- [ ] vider le transport, **vérifier la livraison locale**, puis basculer le MX
- [ ] vidage de la source avec `--delete1`, jamais `--delete2` après bascule
- [ ] contrôler par le verdict d'imapsync, pas par des totaux maison
