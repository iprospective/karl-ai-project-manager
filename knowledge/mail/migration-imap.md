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

## Le séparateur de hiérarchie : relevez celui de la source

Celui-ci a coûté trois jours d'usage dégradé à une cliente, et il est invisible
à toutes les vérifications qu'on pense à faire.

L'ancien serveur exposait `/` comme séparateur de hiérarchie. Le nouveau, sans
réglage explicite, a pris le défaut du format Maildir : `.`. Les messages
étaient tous là, les dossiers aussi, les mots de passe bons — mais les clients
déjà configurés continuaient d'envoyer les chemins avec l'ancien séparateur :

```
UID COPY 205 "COMPTA - ADMINITRATIF/AUDREY":
   NO [CANNOT] Invalid mailbox name: Name must not have '/' characters
```

Plus aucun déplacement vers un **sous-dossier** n'aboutissait, sur tous les
postes. Un dossier de premier niveau, lui, passait — son chemin ne contient pas
de séparateur. D'où un symptôme déroutant : « certains dossiers seulement ».

**Relevez le séparateur de la source avant la bascule**, et posez-le
explicitement sur la cible :

```sh
# côté source, la réponse à LIST donne le séparateur entre guillemets
#   * LIST (\HasNoChildren) "/" "INBOX/Archives"
#                           ^^^
# côté cible, dans le namespace :
#   separator = /
```

Les noms sur disque ne changent pas : Dovecot traduit `/` ↔ `.` en interne. Il
n'y a rien à reconfigurer sur les postes, et surtout rien à refaire — ni
comptes, ni signatures, ni resynchronisation complète.

**Un webmail qui fonctionne n'innocente pas le serveur.** C'est ce qui nous a
égarés le plus longtemps : Roundcube marchait parfaitement, puisqu'il lit le
séparateur annoncé à chaque session. Un client installé de longue date, lui,
garde celui de l'ancien serveur. L'écart entre les deux est précisément le
signal — pas une raison de conclure que le serveur va bien.

## Quand le serveur ne dit rien, capturer plutôt que supposer

Dovecot ne journalise pas les commandes refusées : un `MOVE` qui échoue ne
laisse **aucune trace** au niveau par défaut. On peut donc chercher longtemps
dans `mail.log` une erreur qui n'y sera jamais.

```
# /etc/dovecot/conf.d/99-debug-<boîte>.conf — temporaire, à retirer après
log_debug = user="sandrine@exemple.fr"
debug_log_path = /var/log/dovecot-debug-sandrine.log
```

Filtré sur une seule boîte, cela ne journalise personne d'autre et n'écrit
aucun contenu de message. Chaque commande apparaît avec sa réponse :

```
Debug: Command finished: UID FETCH 201 (BODY.PEEK[]): OK Fetch completed.
Debug: Command finished: UID COPY 205 "A/B": NO [CANNOT] Invalid mailbox name…
```

Vingt minutes de capture ont tranché ce que deux heures d'hypothèses n'avaient
pas résolu. Le réflexe à prendre : dès qu'un symptôme client n'a pas d'écho
dans les logs, c'est la capture qu'il faut mettre en place, pas une hypothèse
de plus. Guillemets obligatoires autour de l'adresse, sinon le filtre est
refusé — et tant qu'il l'est, la configuration ne passe plus un `reload`.

**Et une anomalie trouvée en chemin n'est pas une explication.** Nous avions
trouvé 19 dossiers au nom en NFD, réellement cassés et prouvés tels, dont nous
avons fait la cause de l'incident — avant que la cliente ne précise que les
dossiers en cause n'avaient aucun accent. Vérifier qu'une anomalie rend compte
du symptôme observé coûte une question ; s'en passer coûte une demi-journée.

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

## Résidus de vidage : les doublons de la source

Après `--delete1`, 99 messages sont restés sur la source dans 7 boîtes, alors
qu'`imapsync` annonçait `0 messages found in host1 not in host2`.

Ce sont les **exemplaires en double de la source**. imapsync dédoublonne : quand
un dossier source contient plusieurs fois le même message, il n'en copie qu'un.
Et `--delete1` ne supprime que les messages **appariés un pour un** — les
exemplaires surnuméraires n'ont pas de correspondant à destination, donc il les
laisse. Le log le dit, dossier par dossier :

```
Host1: folder [Sent] selected 240 messages, duplicates 3
Host2: folder [Sent] selected 237 messages, duplicates 0
```

240 − 3 = 237, et cette boîte avait exactement 3 résidus dans `Sent`. La somme
des `duplicates` du log de vidage correspondait, boîte par boîte, aux résidus
constatés — 99 des deux côtés.

Ce n'est donc ni une perte ni une anomalie, mais un nettoyage : les utilisateurs
retrouvent un exemplaire là où la source en avait deux ou trois. Pour le compter
avant de s'inquiéter :

```sh
grep -o 'Host1: folder .* duplicates [1-9][0-9]*' <log> | sed 's/.*duplicates //' \
  | awk '{s+=$1} END {print s+0}'
```

**Deux fausses pistes à ne pas reprendre.** On a d'abord cru aux noms de dossiers
à accent décomposé (`TRE&AwE-SORS` côté source contre `TRÉSORS` côté
destination) : 94 des 99 résidus étaient dans des dossiers sans aucun accent.
Puis à un écart de taille empêchant l'appariement, après avoir mesuré 2 à 4
octets de différence sur 12 d'entre eux : c'est une conséquence et non une cause,
ces douze-là sont des quasi-doublons, même Message-ID reçu par deux chemins.
Les deux hypothèses étaient plausibles et fausses ; **le log d'imapsync
contenait la réponse depuis le début.**

## Purger les dossiers de la source, une fois les messages partis

Vider les messages ne vide pas l'arborescence : sur cette migration il restait
686 dossiers pour 24 boîtes, dont 525 créés par les utilisateurs au fil des ans.
Les supprimer n'est utile que pour une raison : **toute vérification ultérieure
parcourt les dossiers un par un**, et 500 dossiers vides coûtent plusieurs
minutes à chaque passe.

Ce qu'on garde, et comment le reconnaître **sans deviner d'après le nom** :

- `INBOX` ;
- tout dossier portant un attribut IMAP **SPECIAL-USE** — `\Sent`, `\Drafts`,
  `\Junk`, `\Trash`, `\Archive` — que le `LIST` donne gratuitement ;
- les noms standards **au premier niveau seulement**, pour attraper ceux que le
  serveur n'a pas étiquetés : `Sent Messages`, `Deleted Messages`, `Notes`,
  `Spam`, et leurs formes françaises `Éléments envoyés`, `Éléments supprimés`,
  `Brouillons`, `Envoyés`, `Corbeille` ;
- **`dovecot` et `dovecot/sieve`** : ce n'est pas du courrier mais le répertoire
  des filtres Sieve, que la source expose comme un dossier IMAP quand le home est
  un Maildir. Les supprimer effacerait les règles de tri des utilisateurs.

Le premier niveau compte : un `Archives` à la racine est le dossier standard,
un `AA FOURNISSEURS/401 ARCHIVES DIVERS` est un dossier métier. Une recherche
par sous-chaîne confondrait les deux.

Deux précautions dans le script :

- **trier par profondeur décroissante** — supprimer les feuilles avant leurs
  parents, sinon le serveur transforme le parent en `\Noselect` au lieu de le
  supprimer, et il reste dans l'arbre ;
- **re-sélectionner chaque dossier juste avant son `DELETE`** et ne le supprimer
  que si le serveur le trouve vide à cet instant. La liste a pu être établie
  plusieurs minutes plus tôt, et entre-temps un message a pu arriver.

Même principe pour les messages : supprimer par **UID précis**, jamais « tout le
dossier », et relire le Message-ID de chaque UID juste avant de poser `\Deleted`
— c'est ce qui garantit qu'on ne supprime pas un message arrivé entre
l'inventaire et la suppression.

## Ce qui continue d'arriver sur l'ancien serveur

La bascule du MX ne tarit pas la source. Deux fuites, trouvées parce que deux
messages inconnus de la destination sont apparus pendant la purge finale :

- **les domaines secondaires.** Le MX de `calicote.com` était basculé, celui de
  `calicote.fr` non — et personne ne regardait plus la source. Lister *tous* les
  domaines de l'ancien serveur et vérifier le MX de chacun, pas seulement celui
  du domaine principal. Attention au piège : déclarer le domaine secondaire à
  destination ne suffit pas, il lui faut aussi ses **alias** (un catch-all
  `@dom.fr → @dom.com` suffit), sinon la bascule du MX transforme une fuite
  silencieuse en « User unknown ».
- **les équipements qui envoient en SMTP authentifié.** Un scanner, une
  imprimante multifonction, une application métier ont un compte sur l'ancien
  serveur et continuent de lui soumettre leur courrier, MX ou pas. Ici un Xerox
  posté depuis le site du client vers `mail.<ancien>` avec un compte local.
  Inventorier ces expéditeurs **avant** la bascule, dans les logs de la source :
  ce sont eux qui restent branchés le plus longtemps.

Pour les quelques messages déjà tombés dans le trou, `doveadm save -u <boîte>
-m INBOX < message.eml` les dépose à destination ; la date interne devient celle
de l'import, l'en-tête `Date:` reste juste et les clients trient dessus.

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
- `doveadm fetch 'hdr.<nom>'` restitue l'en-tête **tel qu'il est dans le
  message**, repli compris : un `Message-ID:` plié par Outlook sort sur deux
  lignes, la première vide. Un parseur naïf en ligne à ligne perd ces
  valeurs-là — ici 6 256 sur 31 112, soit une « absence » massive et purement
  imaginaire. Recoller les lignes de continuation (celles qui commencent par une
  espace ou une tabulation) avant de comparer.
- `size.physical` est la taille **sur disque** (fins de ligne en LF),
  `size.virtual` la taille **RFC822** (CRLF). Comparer un `size.physical` de
  Dovecot à un `RFC822.SIZE` d'IMAP donne un écart systématique d'environ 1,3 %
  — un octet par ligne — qu'on prend pour une troncature. Comparer
  `size.virtual`.

## Checklist

- [ ] relever le **séparateur de hiérarchie** de la source et le poser sur la cible
- [ ] tester `doveadm auth test` sur **chaque** boîte avec le mot de passe du coffre
- [ ] vérifier les certificats servis par **dovecot ET postfix** (993, 143, 25, 587, 465)
- [ ] poser le hook `letsencrypt/renewal-hooks/deploy/` qui recharge dovecot et postfix
- [ ] vérifier `submission_relay_host` si dovecot occupe le 587
- [ ] créer les alias techniques (`*-www@`) pour que les avis de non-remise aient une boîte
- [ ] faire arrêter l'usage, puis : inventaire du delta → remontée → **miroir** → snapshot
- [ ] vider le transport, **vérifier la livraison locale**, puis basculer le MX
- [ ] vidage de la source avec `--delete1`, jamais `--delete2` après bascule
- [ ] contrôler par le verdict d'imapsync, pas par des totaux maison
- [ ] vérifier le MX de **tous** les domaines de la source, pas seulement le principal
- [ ] inventorier les équipements qui soumettent en SMTP authentifié sur la source
- [ ] purger les dossiers de la source en épargnant les SPECIAL-USE et `dovecot/sieve`
