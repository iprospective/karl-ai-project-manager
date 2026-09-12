# Supervision

Le menu 🩺 **Supervision** montre ce que l'observateur du parc rapporte, et permet d'ouvrir un ticket
**chez le bon client** quand quelque chose casse.

## L'observateur est un fournisseur

Il se déclare comme les autres, dans 🔧 réglages → 🔌 Fournisseurs, sur l'axe **Observateurs** : une URL,
un type, et un jeton posé en écriture seule. Zabbix est le premier type livré ; Uptime Kuma est déclaré
pour le jour où l'on voudra observer des **sites** plutôt que des machines. Le cockpit ne parle jamais à
l'outil de supervision : il demande au serveur, qui sait lequel répond et détient sa clé.

## Alertes

Une ligne par alerte active : sa sévérité, l'hôte, l'intitulé, depuis combien de temps, et **le client ou
projet associé à cet hôte**. Le filtre du haut règle le seuil de gravité et se retient d'une fois sur
l'autre.

L'observateur rapporte, il ne diagnostique pas. Une alerte dit qu'un seuil est franchi, pas pourquoi :
vérifier les métriques avant de conclure sur une cause.

## Ouvrir un ticket depuis une alerte

Le bouton **＋ ticket** crée le ticket dans le client et le projet associés à l'hôte, avec l'alerte, sa
sévérité et sa durée en description. Une confirmation dit chez qui et pour quoi, avant d'agir.

Le bouton n'apparaît que si l'hôte est associé à un **client et un projet**. Sinon la ligne propose
d'aller associer l'hôte : sans projet, on ne saurait pas où créer le ticket, et un ticket chez le mauvais
client ne se rattrape pas.

## Hôtes et association

L'onglet **🖥 Hôtes & association** liste ce qui est supervisé. L'association d'un hôte à un client se
**propose** toute seule — le nom d'hôte porte souvent son domaine — et se **confirme** à la main.

Une association proposée s'affiche en pointillé, avec au survol la règle qui l'a suggérée : le slug du
client, ou un domaine cité dans ses fiches. Tant qu'elle n'est pas confirmée, elle peut se tromper.
Confirmer une association la fige : aucune règle ne la réécrit ensuite. Un hôte peut être détaché.

Le **client** et le **projet** se choisissent tous les deux dans une liste — rien à taper. La liste des
projets suit le client sélectionné, et se met à jour dès qu'on en change. Un client qui a plusieurs
projets exige qu'on en désigne un : sans projet, le bouton de création de ticket ne pourrait pas
aboutir, autant le dire au moment de l'association plutôt que devant une alerte.

## Ce qui n'est pas dans ce lot

Acquitter une alerte depuis le cockpit — cela touche l'outil de toute l'équipe, ça se décide. Et la
supervision des sites au sens URL, qui demande d'abord de savoir ce qu'est un site pour un projet.
