# Runbook — bot Telegram de karl (`karl-telegram-bot.py`)

> Exploitation du « standardiste » Telegram de karl-pm (épic RM1724, sécurité RM1777).
> Le bot ne raisonne pas : il relaie Telegram ↔ Redmine (`/rm`, `/mine`, `/recent`,
> `/search`, `/note`, `/today`). Il ne tourne aujourd'hui sur aucune machine : ce guide
> sert à le mettre en service et à l'administrer.

## Les deux facteurs

1. **Qui peut parler au bot** — la liste blanche. Elle est formée des utilisateurs
   déclarés dans `telegram.users` (voir plus bas) et, en repli, de `TELEGRAM_WHITELIST`.
   **Vide, elle n'autorise personne** : seul `/whoami` répond, pour qu'un nouvel
   arrivant trouve son identifiant. (Avant RM1777, une liste vide laissait tout
   compte Telegram interroger Redmine.)
2. **Le verrou** — un mot de passe, même quand le téléphone est déverrouillé entre de
   mauvaises mains. Verrouillé par défaut et à chaque redémarrage, re-verrouillage
   après 5 min d'inactivité, blocage 5 min après 3 échecs. Le message `/unlock` est
   effacé de la conversation dès réception.

## Mise en service

1. Créer le bot auprès de **@BotFather**, garder le jeton.
2. Poser les secrets **au coffre**, jamais en clair sur la ligne de commande :
   - jeton : `TELEGRAM_BOT_TOKEN` dans le `.env` de l'instance ;
   - verrou : `python3 scripts/karl-telegram-bot.py --hash-password` (saisie masquée,
     deux fois). Ranger l'**empreinte** affichée dans une entrée du coffre, champ
     `password` (ex. `telegram/karl-lock`), puis dans le `.env` :
     `TELEGRAM_LOCK_PASSWORD_HASH=secret:telegram/karl-lock`.
     L'URI suit la cascade de coffre du projet (RM2662) ; `secret://<instance>/…` et
     `vaultwarden://…` sont aussi acceptés.
3. Déclarer les utilisateurs (section suivante).
4. Lancer `python3 scripts/karl-telegram-bot.py` et lire l'en-tête : nombre d'ID
   autorisés, verrou actif, et **origine de l'empreinte** — `coffre`, ou `.env` si
   l'empreinte y est encore en clair (accepté, mais signalé : à migrer).

**Coffre fermé au démarrage** : le bot **refuse de démarrer** (« empreinte du verrou
illisible »). C'est voulu : tourner sans verrou parce que le coffre est fermé
changerait une panne en faille. Ouvrir le coffre, relancer.

## Ajouter un utilisateur

1. La personne écrit `/whoami` au bot. Il répond son `telegram_user_id` et
   « Non reconnu ».
2. Ajouter une entrée dans **`pm.config.local.yml`** — propre à l'instance, jamais
   commitée : un identifiant Telegram est une donnée personnelle.

   ```yaml
   telegram:
     users:
       - telegram_id: 123456789   # entier, tel que /whoami l'a donné
         pm_user: iprospective    # identifiant PM (team.username) : auteur des /note
         redmine_id: 5            # la cible de « /today moi »
         name: Mathieu            # affichage
   ```

   Un `telegram_id` qui n'est pas un entier (ex. entre guillemets) est **ignoré et
   signalé** au démarrage — il n'autorise personne.
3. Redémarrer le bot (la conf est lue au démarrage).
4. Vérifier : `/whoami` répond « Reconnu : <nom> » ; `/status` répond « Verrouillé » ;
   `/unlock <mdp>` ouvre ; `/today moi` donne le bilan de **cette** personne.

**Retirer un utilisateur** : supprimer l'entrée (et son ID de `TELEGRAM_WHITELIST` s'il
y figure), redémarrer. **Changer le mot de passe** : régénérer l'empreinte, la remplacer
au coffre, redémarrer — l'ancien cesse de fonctionner.

## Ce que le bot journalise

La commande seulement, jamais le texte : un inconnu qui taperait `/unlock <mdp>` ne
laisse pas son mot de passe dans les journaux. Refus, succès et échecs de
déverrouillage, et déclenchement du blocage, sont tracés avec l'identifiant Telegram.

Tests : `scripts/test_karl_telegram_bot.py`.
