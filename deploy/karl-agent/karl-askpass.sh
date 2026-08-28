#!/bin/sh
# karl-askpass.sh — programme d'assistance de `ssh-add`, appelé par karl-agent
# (RM2748) pour charger une clé sans terminal.
#
# `ssh-add` ne lit pas de passphrase sur son entrée standard : quand il n'a pas
# de terminal, il exécute $SSH_ASKPASS et lit ce que ce programme écrit. Celui-ci
# lit un **descripteur hérité**, ouvert par l'appelant sur un tube anonyme. La
# passphrase ne passe donc ni par argv (visible dans `ps`), ni par
# l'environnement (`/proc/<pid>/environ`), ni par un fichier temporaire.
#
# RM2822 : le NUMÉRO de ce descripteur se dit dans $KARL_ASKPASS_FD. Il valait 3
# en dur, ce qui supposait que le tube de l'appelant tombe justement sur 3 — vrai
# dans un processus nu, faux dans karl-agent, dont les sockets occupent déjà les
# descripteurs bas : l'askpass lisait alors un descripteur inexistant
# (« Bad file descriptor ») et tout chargement de clé échouait. Le numéro d'un
# descripteur n'est pas un secret ; la passphrase, elle, reste dans le tube.
#
# L'argument que ssh-add passe (le libellé de l'invite) est ignoré volontairement.
#
# Usage (côté appelant) : SSH_ASKPASS=<ce script> SSH_ASKPASS_REQUIRE=force
#                         KARL_ASKPASS_FD=<n> ssh-add <clé>   (tube hérité sur n)
fd="${KARL_ASKPASS_FD:-3}"
case "$fd" in
  ''|*[!0-9]*) echo "karl-askpass: KARL_ASKPASS_FD invalide" >&2; exit 2 ;;
esac
# `<&$fd` ne sait pas lire au-delà du descripteur 9 (dash : « Bad fd number ») —
# or c'est justement là que tombe le tube d'un serveur. On passe donc par
# /dev/fd, qui n'a pas cette limite ; la redirection reste le repli des shells
# ou des systèmes qui ne l'exposent pas (fd ≤ 9 par construction).
if [ -r "/dev/fd/$fd" ]; then
  cat "/dev/fd/$fd"
else
  eval "cat <&$fd"
fi
