#!/usr/bin/env bash
# Installe karl-agent + son tunnel comme services systemd USER sur le LXC `dev`.
# Idempotent. À lancer EN TANT QUE mathieu DANS le conteneur `dev` (pas en root,
# pas sur l'host) : ssh mathieu@dev.lxc puis exécuter ce script.
#
# Prérequis (vérifiés ci-dessous) : python3, tmux, autossh, et un moteur d'agent
# (claude ou opencode) dans le PATH ; alias SSH `mmi` joignable depuis `dev`.
set -euo pipefail

REPO="/zfs/workspaces/ai/project-management"
UNIT_SRC="$REPO/deploy/karl-agent"
UNIT_DST="$HOME/.config/systemd/user"

echo "==> Vérification des prérequis"
need() { command -v "$1" >/dev/null 2>&1 || { echo "  MANQUANT : $1"; MISSING=1; }; }
MISSING=0
need python3
need tmux
need autossh
command -v claude >/dev/null 2>&1 || command -v opencode >/dev/null 2>&1 || {
  echo "  MANQUANT : moteur d'agent (claude ou opencode)"; MISSING=1; }
if [ "$MISSING" = 1 ]; then
  echo "Installe les paquets manquants puis relance. (ex : sudo apt install tmux autossh)"
  exit 1
fi

# ttyd est OPTIONNEL : il alimente le terminal web du cockpit (RM1873). Son
# absence n'empêche pas karl-agent ni la page cockpit de tourner (seul l'attach
# navigateur est indisponible). On ne bloque donc pas dessus.
#
# VERSION ÉPINGLÉE (RM2323) : ttyd < 1.7.5 embarque xterm.js 4.x, dont la gestion
# de la saisie COMPOSÉE (caractères accentués « é/à/ç », dead keys, IME) est
# boguée — il faut s'y reprendre plusieurs fois pour un « é » dans le terminal
# web. ttyd 1.7.5 est passé à xterm.js 5.4.0 + addon Unicode 11 (tsl0922/ttyd
# #1303/#1310), qui corrige cette classe de bug. On installe donc un binaire
# statique RÉCENT et VÉRIFIÉ dans ~/.local/bin (sans root, sans apt), plutôt que
# `apt install ttyd` (version aléatoire souvent trop ancienne + piège du service
# système homonyme qui squatte le port 7681, cf. plus bas).
TTYD_PIN="1.7.7"        # version cible (dernière 1.7.x au 2026-07)
TTYD_MIN="1.7.5"        # plancher : première avec xterm 5.4.0 (fix accents)
# SHA256 officiels de la release 1.7.7 (github.com/tsl0922/ttyd/releases → SHA256SUMS)
TTYD_SHA_x86_64="8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55"
TTYD_SHA_aarch64="b38acadd89d1d396a0f5649aa52c539edbad07f4bc7348b27b4f4b7219dd4165"

# vrai si $1 (version X.Y.Z) >= $2, via tri sémantique (sort -V)
_ver_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]; }
_ttyd_ver() { command -v ttyd >/dev/null 2>&1 && ttyd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1; }

ensure_ttyd() {
  local cur asset sha tmp
  cur="$(_ttyd_ver || true)"
  if [ -n "$cur" ] && _ver_ge "$cur" "$TTYD_MIN"; then
    echo "  ttyd $cur (>= $TTYD_MIN : saisie accentuée OK, RM2323)"; HAVE_TTYD=1; return
  fi
  if [ "${TTYD_NO_MANAGE:-0}" = 1 ]; then
    [ -n "$cur" ] && { echo "  ⚠ ttyd $cur < $TTYD_MIN (accents bogués) — TTYD_NO_MANAGE=1, non modifié"; HAVE_TTYD=1; } \
                  || echo "  (optionnel) ttyd absent — TTYD_NO_MANAGE=1, non installé"
    return
  fi
  case "$(uname -m)" in
    x86_64)  asset="ttyd.x86_64";  sha="$TTYD_SHA_x86_64" ;;
    aarch64) asset="ttyd.aarch64"; sha="$TTYD_SHA_aarch64" ;;
    *) echo "  ⚠ arch $(uname -m) sans binaire ttyd épinglé — installe ttyd >= $TTYD_MIN à la main (accents, RM2323)"
       [ -n "$cur" ] && HAVE_TTYD=1; return ;;
  esac
  [ -n "$cur" ] && echo "  ttyd $cur < $TTYD_MIN → mise à niveau vers $TTYD_PIN (fix accents RM2323)" \
                || echo "  ttyd absent → installation $TTYD_PIN dans ~/.local/bin (fix accents RM2323)"
  tmp="$(mktemp)"
  if ! curl -fsSL --max-time 60 -o "$tmp" \
        "https://github.com/tsl0922/ttyd/releases/download/${TTYD_PIN}/${asset}"; then
    echo "  ⚠ téléchargement ttyd échoué (réseau ?) — cockpit sans attach navigateur"
    rm -f "$tmp"; [ -n "$cur" ] && HAVE_TTYD=1; return
  fi
  if [ "$(sha256sum "$tmp" | cut -d' ' -f1)" != "$sha" ]; then
    echo "  ✗ checksum ttyd invalide — installation ABANDONNÉE (binaire non fiable)"
    rm -f "$tmp"; [ -n "$cur" ] && HAVE_TTYD=1; return
  fi
  mkdir -p "$HOME/.local/bin"
  # sauvegarde l'ancien binaire user (rollback) avant de l'écraser
  [ -f "$HOME/.local/bin/ttyd" ] && cp -a "$HOME/.local/bin/ttyd" "$HOME/.local/bin/ttyd.pre-${TTYD_PIN}.bak"
  install -m 0755 "$tmp" "$HOME/.local/bin/ttyd"; rm -f "$tmp"
  hash -r 2>/dev/null || true
  echo "  ✓ ttyd $(_ttyd_ver) installé (~/.local/bin/ttyd, SHA256 vérifié)"; HAVE_TTYD=1
}

HAVE_TTYD=0
ensure_ttyd

# PIÈGE CONNU (vécu sur dev, RM1873) : le paquet `ttyd` (apt) installe ET active
# tout seul un service SYSTÈME `ttyd.service` qui lance `ttyd -p 7681 -O login`
# (un login web) → il squatte le port 7681 et NOTRE ttyd user (qui fait
# `attach-karl.sh`) ne peut plus binder (EADDRINUSE, crash-loop). Symptôme dans
# le navigateur : un prompt « <host> login: » au lieu du TUI de l'agent.
# `systemctl is-enabled/is-active` SANS --user interroge le manager système :
# il voit le service du paquet, pas le nôtre (homonyme, scope user).
if systemctl is-enabled ttyd.service >/dev/null 2>&1 || systemctl is-active ttyd.service >/dev/null 2>&1; then
  echo "  ⚠ Le service SYSTÈME ttyd.service (paquet apt) occupe le port 7681."
  echo "    Neutralise-le (root) AVANT que notre ttyd user puisse démarrer :"
  echo "      sudo systemctl disable --now ttyd.service && sudo systemctl mask ttyd.service"
fi

echo "==> Test de l'alias SSH 'mmi' (tunnel)"
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 mmi true 2>/dev/null; then
  echo "  ATTENTION : 'ssh mmi' ne répond pas en BatchMode. Vérifie ~/.ssh/config"
  echo "  et la clé autorisée côté mmi avant d'activer karl-agent-tunnel.service."
fi

echo "==> Installation des units dans $UNIT_DST"
mkdir -p "$UNIT_DST"
cp "$UNIT_SRC/karl-agent.service"          "$UNIT_DST/"
cp "$UNIT_SRC/karl-agent-tunnel.service"   "$UNIT_DST/"
cp "$UNIT_SRC/ttyd.service"                "$UNIT_DST/"
# RM2376 : watchdog auth SSH GitLab (« karl peut-il pousser ? ») — timer 15 min
cp "$UNIT_SRC/karl-gitlab-check.service"   "$UNIT_DST/"
cp "$UNIT_SRC/karl-gitlab-check.timer"     "$UNIT_DST/"
systemctl --user daemon-reload

echo "==> Activation du linger (survie aux reboots sans session ouverte)"
if ! loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
  loginctl enable-linger "$USER" || echo "  (enable-linger a échoué — peut nécessiter root une fois)"
fi

echo "==> Activation + démarrage des services"
systemctl --user enable --now karl-agent.service
systemctl --user enable --now karl-agent-tunnel.service
# RM2376 : watchdog GitLab — timer périodique (le .service oneshot est lancé par lui)
systemctl --user enable --now karl-gitlab-check.timer
systemctl --user start karl-gitlab-check.service 2>/dev/null || true  # premier état tout de suite
if [ "$HAVE_TTYD" = 1 ]; then
  systemctl --user enable --now ttyd.service
  # RM2323 : si le binaire vient d'être mis à niveau, un restart charge la
  # nouvelle version (le service déjà lancé tourne encore sur l'ancienne).
  systemctl --user restart ttyd.service 2>/dev/null || true
else
  echo "  ttyd indisponible : ttyd.service installé mais NON démarré."
  echo "  Relance ce script une fois le réseau rétabli (il pose ttyd >= $TTYD_MIN tout seul)."
fi

echo "==> État"
systemctl --user --no-pager status karl-agent.service karl-agent-tunnel.service || true
[ "$HAVE_TTYD" = 1 ] && systemctl --user --no-pager status ttyd.service || true
echo
echo "OK. Test local :   curl -s http://127.0.0.1:9876/health"
echo "Test depuis mmi :  ssh mmi 'curl -s http://127.0.0.1:9876/health'"
echo
echo "Cockpit web (LOCAL uniquement tant que l'auth RM1845 n'est pas en place) :"
echo "  depuis le laptop :  ssh -L 9876:localhost:9876 -L 7681:localhost:7681 dev.lxc"
echo "  puis navigateur :   http://localhost:9876/"
