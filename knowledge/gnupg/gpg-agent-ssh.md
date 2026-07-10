---
type: knowledge
product: gnupg
created: 2026-07-10
---

# gpg-agent en émulation ssh-agent — pièges en headless (LXC)

## Le problème

Sur Debian/Ubuntu, le paquet `gpg-agent` active **par preset systemd global**
`gpg-agent-ssh.socket` (user scope), qui pose `SSH_AUTH_SOCK` vers
`$XDG_RUNTIME_DIR/gnupg/S.gpg-agent.ssh` au login. Tout `ssh`/`ssh-add` parle alors à
gpg-agent **sans que personne ne l'ait choisi** (rien dans `.bashrc` ; `gpg-agent.conf`
n'a même pas besoin de `enable-ssh-support` — c'est le socket systemd qui active le rôle).

Ce montage est pensé pour les clés d'auth **stockées dans GPG** (carte à puce/YubiKey,
sous-clé [A]). Pour une clé RSA classique de `~/.ssh` sur une machine **headless** (LXC),
il casse : `ssh-add` échoue avec **`agent refused operation`** (au chargement de la clé ou
à la signature — pinentry/sshcontrol fragiles sans session graphique). Symptôme sournois
en batch : `sign_and_send_pubkey: signing failed ... agent refused operation` après
expiration du cache (TTL ssh du gpg-agent ~10 min par défaut), alors qu'un `ssh-add` venait
de marcher.

## Diagnostic rapide

```bash
echo $SSH_AUTH_SOCK              # …/gnupg/S.gpg-agent.ssh ⇒ gpg-agent est aux commandes
systemctl --user is-active gpg-agent-ssh.socket
gpg -K                           # aucune clé secrète GPG ? ⇒ l'émulation ne sert à rien
cat ~/.gnupg/sshcontrol          # vide ? ⇒ aucune clé ssh gérée par gpg
```

Si aucune clé GPG secrète ni carte : l'émulation est du pur défaut de distro, la
désactiver ne perd rien (GPG lui-même — `gpg-agent.socket` — reste intact).

## Remède : vrai ssh-agent user (fait sur dev.lxc, 2026-07-09)

```bash
# 1. neutraliser l'émulation (mask : le socket est enabled en scope GLOBAL,
#    un simple disable user reviendrait au prochain login)
systemctl --user mask --now gpg-agent-ssh.socket

# 2. ssh-agent user sur socket fixe
cat > ~/.config/systemd/user/ssh-agent.service <<'EOF'
[Unit]
Description=SSH authentication agent
[Service]
Type=simple
ExecStart=/usr/bin/ssh-agent -D -a %t/ssh-agent.sock
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload && systemctl --user enable --now ssh-agent.service

# 3. SSH_AUTH_SOCK au login
mkdir -p ~/.config/environment.d
echo 'SSH_AUTH_SOCK=${XDG_RUNTIME_DIR}/ssh-agent.sock' > ~/.config/environment.d/ssh-agent.conf
# + garde .bashrc pour les shells non-login :
# export SSH_AUTH_SOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/ssh-agent.sock"
```

Pièges post-bascule :
- Les **shells déjà ouverts** gardent l'ancien `SSH_AUTH_SOCK` → `export` manuel ou
  nouveau shell.
- Un `ssh -A` entrant **écrase** `SSH_AUTH_SOCK` avec le socket forwardé (normal) ; à la
  déconnexion du forward, un shell qui a hérité de ce socket est orphelin
  (`Error connecting to agent: Permission denied`).

Réversible : `systemctl --user unmask gpg-agent-ssh.socket && systemctl --user disable
--now ssh-agent.service` (+ retirer environment.d/bashrc).

NB : la distro fournit `/usr/lib/systemd/user/ssh-agent.service` (openssh-client) mais il
est conditionné X11 (`ConditionPathExists=/etc/X11/Xsession.options`) — inutilisable en
headless, d'où l'unité custom.
