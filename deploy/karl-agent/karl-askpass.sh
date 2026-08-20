#!/bin/sh
# karl-askpass.sh — programme d'assistance de `ssh-add`, appelé par karl-agent
# (RM2748) pour charger une clé sans terminal.
#
# `ssh-add` ne lit pas de passphrase sur son entrée standard : quand il n'a pas
# de terminal, il exécute $SSH_ASKPASS et lit ce que ce programme écrit. Celui-ci
# lit le **descripteur 3**, ouvert par l'appelant sur un tube anonyme. La
# passphrase ne passe donc ni par argv (visible dans `ps`), ni par
# l'environnement (`/proc/<pid>/environ`), ni par un fichier temporaire.
#
# L'argument que ssh-add passe (le libellé de l'invite) est ignoré volontairement.
#
# Usage (côté appelant) : SSH_ASKPASS=<ce script> SSH_ASKPASS_REQUIRE=force
#                         ssh-add <clé>   3<&<tube>
cat <&3
