# Verrous : coffre de secrets et clés SSH

Deux verrous conditionnent presque tout le reste : le **coffre de secrets**
(mots de passe des clients, jetons, accès serveurs) et l'**agent SSH** (clés
d'accès aux machines). Tous deux s'ouvrent avec un secret que **toi seul**
connais, et se referment tout seuls — après un temps d'inactivité, la nuit, ou
au redémarrage de la machine.

Quand l'un des deux est fermé, un bouton **🔓 déverrouiller** apparaît en haut du
cockpit. Il n'est là que dans ce cas : s'il n'y est pas, tout est ouvert.

## Ouvrir le coffre

1. Clic sur **🔓 déverrouiller** — l'état de chaque coffre s'affiche.
2. Tape le **mot de passe maître**, valide.
3. Le bouton disparaît : le coffre est ouvert, les agents peuvent de nouveau
   résoudre les secrets dont ils ont besoin.

Si tu as plusieurs coffres (un par client, par exemple), choisis celui à ouvrir :
déverrouiller l'un n'ouvre pas les autres.

## Charger une clé SSH

Même écran, section **🔑 Agent SSH** : choisis la clé (celles de `~/.ssh` sont
proposées), tape sa passphrase, **Charger**. Les clés déjà chargées sont listées
au-dessus — inutile d'en recharger une.

## Ce qu'il advient de ce que tu tapes

- Le mot de passe **n'est pas mémorisé** : il sert à ouvrir, puis il est oublié.
  Ni le navigateur, ni le serveur ne le gardent — il n'y a pas de « retenir ».
- Il ne s'écrit **nulle part** : ni dans un journal, ni dans un fichier, ni dans
  la liste des processus de la machine.
- Le formulaire ne s'affiche **qu'en connexion sécurisée** (https, ou depuis la
  machine elle-même). En clair, il refuse de te faire saisir quoi que ce soit.
- La page ne lit jamais un secret existant : elle ouvre, elle ne consulte pas.

## Quand ça ne marche pas

| Message | Ce que ça veut dire |
|---|---|
| mot de passe refusé | le coffre n'a pas reconnu le mot de passe — rien n'est ouvert |
| agent injoignable | l'agent SSH ne tourne pas : rien à charger tant qu'il n'est pas là |
| délai dépassé | le coffre distant n'a pas répondu — réessaie, puis regarde 🩺 **poste** |

Le panneau 🩺 **poste** donne le diagnostic complet (outils, secrets, git, SSH) et,
pour chaque défaut, la commande exacte à lancer au terminal.

Voir aussi : [Réglages](reglages).
