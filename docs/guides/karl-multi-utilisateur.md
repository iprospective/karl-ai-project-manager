# Runbook — karl en mono ou multi-utilisateur

> Mode d'installation de karl (RM3070). Le mode n'était écrit nulle part : il était **de fait**,
> et chaque composant supposait l'un ou l'autre. Il se déclare maintenant, et l'installation
> réelle est **contrôlée** contre cette déclaration.

## Déclarer le mode

```yaml
install:
  mode: mono        # mono | multi   (défaut : mono)
```

Ordre de résolution : `KARL_INSTALL_MODE` (posé par l'unité de service) > `install.mode` de la
conf > `mono`. Réglable aussi dans le cockpit (réglages → Installation, administrateur seul).
Une valeur inconnue retombe sur `mono` **en le disant**.

Le mode n'est **jamais déduit** de l'environnement. Mais quatre signaux lui sont comparés au
démarrage — compte de service, règle sudoers, code appartenant à root, nombre de comptes
cockpit — et chaque écart est journalisé et exposé par `/health` (`install.warnings`), sans
jamais empêcher le démarrage. Sur une instance mono dont le code appartient à root, l'écart
annoncé est normal : il dit que la mise à jour exigera `sudo`.

## Ce que le mode commande

| | `mono` | `multi` |
|---|---|---|
| Moteur `shell` | ouvert | **administrateurs seuls** (il donne les droits UNIX du compte de service) |
| Coffre, agent SSH (`/vault/*`) | ouvert | **administrateurs seuls** (ils sont partagés par le processus) |
| Liste des sessions | toutes | **les siennes** ; un administrateur voit tout |
| Préférences du navigateur | clés nues | cloisonnées par utilisateur, purgées à la déconnexion |
| Mise à jour (`core-update`) | sans `sudo` si le code vous appartient | `sudo` (code root, verrou 3 couches) |

Le propriétaire d'une session est inscrit dans sa fiche (`keys/<clé>.json`), **pas dans le nom
tmux** : renommer les sessions casserait celles qui tournent, l'attache et la résolution des
worklogs. Les sessions créées avant n'ont pas de propriétaire : elles ne sont attribuées à
personne et restent visibles des administrateurs.

## Passer en multi : une instance par développeur

Une instance de karl par développeur, un front unique devant — le multi devient un problème de
routage, pas une réécriture du superviseur.

```bash
mmi-pm karl-service --user alice --port 9881       # imprime les trois pièces
mmi-pm karl-service --list                         # qui est déclaré, sur quel port
```

Le script **n'écrit rien dans `/etc`** : il rédige, et rappelle les commandes root à lancer
(barrière humaine voulue). Les trois pièces :

1. `/etc/karl-agent/<login>.env` — son port (et son jeton). `0640 root:<login>` ;
2. `/etc/systemd/system/karl-agent@.service` — le gabarit, rendu avec les chemins de l'instance ;
3. le fragment de reverse-proxy qui route `/<login>/` vers son port, **avec
   `upgrade=websocket`** (un `ProxyPass ws://` ne déclenche pas l'upgrade : le backend verrait
   un GET nu, et le terminal ne s'ouvrirait jamais).

Le port est obligatoire et unique : deux instances sur le même port refuseraient de démarrer, et
le message de systemd ne dirait pas laquelle est en cause — le générateur refuse donc le conflit
d'avance, en nommant l'autre développeur.

**Droits sudo** : voir `deploy/mmi-pm.sudoers.example`. Une ligne par capacité, toutes **avec mot
de passe** — pas de `NOPASSWD`. C'est pour cela que le cockpit refuse désormais, en 409 et avec la
commande à taper, les portées qui exigeraient une escalade silencieuse (`.env` global, moteur
installé pour toute la machine).

## Ce qui n'est pas encore fait

- Les **transcripts** d'une session sont cherchés dans le store du compte qui fait tourner le
  démon. Avec une instance par développeur (ci-dessus), chacun lit le sien — mais un démon unique
  ne voit pas ceux des autres, et le `--resume` natif exige de toute façon le transcript dans le
  store du compte qui lance le moteur.
- Le **mail** et les notifications client partent sous l'identité de l'instance, pas du
  développeur : seul l'acteur (`PM_ACTOR_*`) est tracé.
