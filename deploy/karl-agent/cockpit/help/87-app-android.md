# App Android

L'app **karl** pilote ce cockpit depuis un téléphone Android : c'est le site
mobile du cockpit dans une coquille native qui ajoute ce qu'un navigateur ne sait
pas faire — un **jeton d'appareil chiffré** par le téléphone et un
**déverrouillage par empreinte** facultatif.

## Installer

1. Sur le téléphone, ouvrir **[/app/karl-cockpit.apk](/app/karl-cockpit.apk)**
   (depuis ce cockpit, ex. `https://karl.iprospective.fr/app/karl-cockpit.apk`).
2. Autoriser l'installation depuis le navigateur quand Android le demande
   (« sources inconnues » : l'app n'est pas sur le Play Store).
3. Mise à jour : même geste, par-dessus l'app existante (même signature).

## Se connecter

1. **Ajouter un serveur** : l'URL du cockpit, ex. `https://karl.iprospective.fr`
   (HTTP clair accepté seulement pour `*.lxc`, sur le réseau local).
2. **Identifiant + mot de passe**, une seule fois : le mot de passe n'est pas
   conservé, l'app reçoit un jeton propre au téléphone (« App Android / modèle »).
3. Le cockpit s'ouvre ; aux lancements suivants, l'app y retourne directement.

## Menu ⋮ de l'app

| Entrée | Effet |
|---|---|
| **Déverrouillage biométrique** | le jeton n'est lisible qu'après empreinte ; re-demandée au retour sur l'app après 5 min d'absence |
| **Serveurs** | changer de serveur, en ajouter (appui long : modifier / oublier) |
| **Se déconnecter** | révoque le jeton de ce téléphone sur le serveur |

Le téléphone apparaît dans **Réglages → Appareils enregistrés** : le révoquer
d'ici déconnecte l'app, qui redemande les identifiants à la prochaine ouverture.
