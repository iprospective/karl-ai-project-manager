---
type: knowledge
product: opensvc
created: 2026-10-18
---

# Basculer un conteneur d'un nœud à l'autre

Procédure du parc iProspective (opensvc 2.1), dictée par Mathieu et éprouvée sur
le déplacement de `calicote` de srv5 vers srv3 le 18/10/2026 (RM2827, RM3478).

## Les trois étapes

### 1. Arrêter proprement ce qui doit l'être — **optionnel, à arbitrer**

Ce n'est pas une recette mais un choix, selon le **type de conteneur**, s'il est
**en production**, et le **trafic** qu'il porte :

- mise en **maintenance** applicative (page dédiée, gel des écritures) ;
- `om <obj> stopapp` — arrête toutes les ressources `app` ;
- `om <obj> stop --rid app#<nom>` — n'arrête que certaines.

Un conteneur de test, ou un conteneur de production qu'on bascule hors
fréquentation, peut sauter cette étape : `switch` arrête le service de toute
façon. L'intérêt est de **maîtriser l'ordre d'arrêt** quand un applicatif écrit
en continu — une base, une file, un cron long — plutôt que de le laisser couper
au milieu d'une transaction.

### 2. Synchroniser les nœuds esclaves

```sh
om <obj> sync nodes
```

Réplique l'état courant vers les autres nœuds. **À ne pas sauter** : le `switch`
démarre sur la copie locale du nœud cible, et ce qui n'a pas été répliqué est
perdu — silencieusement. Vérifier que le dernier snapshot porte la même date des
deux côtés :

```sh
zfs list -H -t snapshot -o name,creation -s creation <pool>/lxc/<obj> | tail -1
```

### 3. Basculer

```sh
om <obj> switch --to <nœud-cible>
```

La commande **rend la main immédiatement** (`defer target state set to
placed@<nœud>`) : la bascule est asynchrone et prend environ une minute. Suivre
l'état sur les deux nœuds plutôt que de conclure trop vite :

```sh
lxc-ls -f | awk '$1=="<obj>"{print $2}'
```

## Ce qui ne suit pas le conteneur

Le dataset est répliqué, pas l'environnement du nœud. Quatre choses sont à
vérifier **avant** de basculer, sous peine de démarrer un conteneur sans réseau.

### La passerelle dépend de l'hôte

Chaque serveur a la sienne — srv3 : `51.91.80.254`, srv5 : `54.36.122.254`. Le
netplan **du conteneur** porte une route par défaut `on-link` vers celle de
l'hôte où il tournait. Après bascule, elle est fausse.

Laisser un commentaire dans le netplan à côté de la route, pour que le prochain
qui bascule le voie.

### Le bridge d'attache peut différer

`lxc.net.<n>.link` dans `/var/lib/lxc/<obj>/config` nomme un bridge de **l'hôte**,
et leur composition varie d'un nœud à l'autre. Vérifier que le bridge visé
contient bien l'interface attendue :

```sh
ls /sys/class/net/<bridge>/brif/
```

Sur `calicote`, `eth0` était attaché au bridge du **vrack** et non au bridge
public : l'IP publique n'aurait rien servi.

### La configuration LXC doit être identique sur les trois nœuds

`/var/lib/lxc/<obj>/config` est un fichier **de l'hôte**, hors du dataset
répliqué. Une correction faite sur un seul nœud disparaît au failover suivant.
Les trois, systématiquement — c'est la même leçon que pour `cluster.conf` et
pour `fs#root.quota`.

### Une IP failover OVH est liée à un serveur

Si le conteneur porte une IPv4 failover avec **MAC virtuelle**, celle-ci est
rattachée à un serveur dans l'espace client OVH. La basculer vers le nouveau
nœud est une action manuelle, hors du parc.

Jusqu'à ce qu'elle soit faite, **ne pas mettre la route publique par défaut** :
une passerelle injoignable de métrique basse coupe toute sortie, même avec une
route de secours. Garder le NAT `lxcbr0` le temps de la transition, et ne
réactiver la route publique qu'après vérification :

```sh
lxc-attach -n <obj> -- curl -s -4 https://ifconfig.me   # doit renvoyer la failover
```

## Après la bascule

**Les propriétés locales du dataset ne sont pas toujours reprises.** Un réglage
comme `special_small_blocks`, posé pour un pool avec périphérique spécial, n'a
pas de sens sur un nœud dont le pool est intégralement NVMe : le vérifier et
l'ajuster plutôt que de le laisser mentir.

**Le statut des ressources encapsulées se rafraîchit depuis le conteneur.** Une
ressource `encap = true` voit son statut calculé par l'agent *à l'intérieur*,
avec son propre cache. Un `om <obj> print status --refresh` depuis l'hyperviseur
peut continuer d'afficher l'ancienne valeur ; il faut le lancer dans le
conteneur pour que l'hyperviseur la reprenne. Sans cela on croit qu'une
correction n'a pas pris.

**`tags = noaction` sur une ressource `ip`** signifie qu'opensvc l'affiche sans
jamais la monter. Pratique — une valeur erronée n'a aucun effet opérationnel —
mais trompeur : le statut peut annoncer une adresse qui n'est pas celle du
conteneur.

## Vérifications utiles

```sh
# réseau et sortie
lxc-attach -n <obj> -- ip -4 -o addr show
lxc-attach -n <obj> -- ip -4 route show default
lxc-attach -n <obj> -- curl -s -4 https://ifconfig.me

# services
lxc-attach -n <obj> -- systemctl is-active <liste>

# entrée depuis l'extérieur du parc, depuis une machine tierce
for p in 80 443 25 993; do timeout 5 bash -c "echo > /dev/tcp/<ip>/$p" && echo "$p ouvert"; done
```

Et, pour un conteneur applicatif, mesurer les temps de réponse avant et après :
le déplacement de `calicote` de srv5 vers srv3 a fait passer la page d'accueil
PrestaShop de 0,80 s à 0,33 s — l'écart de fréquence monocœur et le NVMe
cumulés. Une bascule peut se justifier par la performance autant que par la
disponibilité.
