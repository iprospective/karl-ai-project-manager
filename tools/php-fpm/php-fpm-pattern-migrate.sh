#!/usr/bin/env bash
#
# php-fpm-pattern-migrate.sh
# --------------------------
# Normalise les pools PHP-FPM sur le "pattern includes" de référence (PHP 8.4) :
#   - default.conf.inc : le www.conf stock, section [www] commentée (includable)
#   - common.conf.inc  : overrides maison ($pool.sock, ondemand, logs /var/log/php/$pool.*)
#   - www.conf         : pool par défaut réécrit en [www-<v>] + include default + include common
#
# Les fichiers .inc canoniques sont SOURCÉS depuis la version de référence (REF_VER).
# Les pools projet existants (calicote, dolibarr, …) NE sont PAS touchés (ils tournent
# déjà sur [nom-<v>] + $pool.sock) : leur conversion au pattern est un chantier séparé.
#
# Sûr par défaut :
#   - DRY-RUN par défaut (n'écrit RIEN sans --apply)
#   - backup tar.gz du pool.d/ avant toute écriture
#   - `php-fpm<v> -t` OBLIGATOIRE après écriture ; échec => restore backup + abort
#   - reload seulement avec --reload ET -t OK
#   - fusion (pas écrasement) d'un common.conf.inc préexistant
#   - garde-fou : refuse de neutraliser un www.conf stock si un vhost référence php<v>-fpm.sock
#
# Usage :
#   php-fpm-pattern-migrate.sh <version|all> [--apply] [--reload|--restart]
#   ex:  php-fpm-pattern-migrate.sh 8.5                  # dry-run
#        php-fpm-pattern-migrate.sh 8.5 --apply --restart  # état propre (recrée socket www)
#        php-fpm-pattern-migrate.sh 7.4 --apply --reload   # pools projet, sans coupure
#        php-fpm-pattern-migrate.sh all                  # dry-run global
# --reload  : SIGUSR2, aucune coupure des pools projet (le www renommé ne flippe qu'au restart)
# --restart : coupure brève, recrée proprement le socket du pool www renommé
#
set -euo pipefail

REF_VER=8.4
BACKUP_DIR=/root/fpm-pattern-backups
ALL_VERS=(5.6 7.2 7.4 8.1 8.2 8.3 8.5)   # toutes sauf REF_VER

APPLY=0; RELOAD=0; RESTART=0; TARGETS=()
for a in "$@"; do
  case "$a" in
    --apply)   APPLY=1 ;;
    --reload)  RELOAD=1 ;;
    --restart) RESTART=1 ;;   # nécessaire pour recréer le socket d'un pool renommé (www)
    all)      TARGETS=("${ALL_VERS[@]}") ;;
    [0-9].[0-9]|[0-9].[0-9][0-9]) TARGETS+=("$a") ;;
    *) echo "arg inconnu: $a" >&2; exit 2 ;;
  esac
done
[ "${#TARGETS[@]}" -gt 0 ] || { echo "usage: $0 <version|all> [--apply] [--reload]" >&2; exit 2; }

ts() { date +%Y%m%d-%H%M%S; }
say() { printf '%s\n' "$*"; }
hr()  { printf -- '---- %s ----\n' "$*"; }
nodot() { echo "${1/./}"; }   # 8.4 -> 84

REF_POOLD="/etc/php/$REF_VER/fpm/pool.d"
[ -f "$REF_POOLD/default.conf.inc" ] && [ -f "$REF_POOLD/common.conf.inc" ] \
  || { echo "ERREUR: .inc de référence absents dans $REF_POOLD" >&2; exit 1; }

migrate_one() {
  local V="$1" VN; VN=$(nodot "$V")
  local PD="/etc/php/$V/fpm/pool.d"
  hr "PHP $V"
  [ -d "$PD" ] || { say "  (non installé, skip)"; return 0; }

  # --- 1) backup ---
  local bk="$BACKUP_DIR/${V}-$(ts).tar.gz"
  if [ "$APPLY" = 1 ]; then
    mkdir -p "$BACKUP_DIR"; tar czf "$bk" -C "$PD" .
    say "  backup: $bk"
  else
    say "  [DRY] backup -> $BACKUP_DIR/${V}-<ts>.tar.gz"
  fi

  # --- 2) default.conf.inc (depuis REF, listen ajusté à la version) ---
  local tmp_default; tmp_default=$(mktemp)
  sed "s#/run/php/php${REF_VER}-fpm.sock#/run/php/php${V}-fpm.sock#g" \
      "$REF_POOLD/default.conf.inc" > "$tmp_default"
  if [ -f "$PD/default.conf.inc" ] && cmp -s "$tmp_default" "$PD/default.conf.inc"; then
    say "  default.conf.inc : déjà à jour"
  elif [ "$APPLY" = 1 ]; then
    cp "$tmp_default" "$PD/default.conf.inc"; say "  default.conf.inc : écrit"
  else
    say "  [DRY] default.conf.inc : (ré)écrirait ($(wc -l <"$tmp_default") lignes)"
  fi

  # --- 3) common.conf.inc (REF + fusion des clés extra préexistantes) ---
  local tmp_common; tmp_common=$(mktemp); cp "$REF_POOLD/common.conf.inc" "$tmp_common"
  local merged=()
  if [ -f "$PD/common.conf.inc" ]; then
    # lignes-directives existantes dont la CLÉ n'est pas déjà dans le common de REF
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      case "$line" in \;*|\#*) continue ;; esac
      local key="${line%%=*}"; key="${key// /}"
      if ! grep -qE "^\s*${key//[/\\[}\s*=" "$REF_POOLD/common.conf.inc"; then
        printf '%s\n' "$line" >> "$tmp_common"; merged+=("$line")
      fi
    done < "$PD/common.conf.inc"
    [ "${#merged[@]}" -gt 0 ] && say "  common.conf.inc : fusion de ${#merged[@]} directive(s) préexistante(s): ${merged[*]}"
  fi
  if [ -f "$PD/common.conf.inc" ] && cmp -s "$tmp_common" "$PD/common.conf.inc"; then
    say "  common.conf.inc : déjà à jour"
  elif [ "$APPLY" = 1 ]; then
    cp "$tmp_common" "$PD/common.conf.inc"; say "  common.conf.inc : écrit"
  else
    say "  [DRY] common.conf.inc : (ré)écrirait"
  fi

  # --- 4) www.conf : neutralisation en [www-<v>] + includes ---
  local www="$PD/www.conf"
  local sec=""; [ -f "$www" ] && sec=$(grep -m1 -E '^\[' "$www" || true)
  if [ "$sec" = "[www-$VN]" ] && grep -qE '^\s*include\s*=' "$www"; then
    say "  www.conf : déjà au pattern"
  else
    # garde-fou : si www stock ([www]) et un vhost pointe sur php<v>-fpm.sock => refuser
    if printf '%s' "$sec" | grep -qxE '\[www\]'; then
      local hits
      # on ne regarde que la conf ACTIVE (sites/conf-enabled), pas conf-available (inerte)
      hits=$(grep -rslE "php${V}-fpm\.sock" \
               /etc/apache2/sites-enabled /etc/apache2/conf-enabled \
               /etc/nginx/sites-enabled 2>/dev/null || true)
      if [ -n "$hits" ]; then
        say "  www.conf : ⛔ NEUTRALISATION REFUSÉE — php${V}-fpm.sock référencé par un vhost ACTIF :"
        printf '             %s\n' $hits
        say "             (un vhost dépend du sock par défaut ; à traiter à la main)"
      else
        neutralize_www "$V" "$VN" "$www"
      fi
    else
      neutralize_www "$V" "$VN" "$www"
    fi
  fi

  rm -f "$tmp_default" "$tmp_common"

  # --- 5) validation + reload ---
  if [ "$APPLY" = 1 ]; then
    if php-fpm"$V" -t 2>/tmp/fpmtest.$V; then
      say "  php-fpm$V -t : OK"
      if [ "$RESTART" = 1 ]; then
        systemctl restart "php${V}-fpm" && say "  restart php${V}-fpm : OK (socket www recréé)"
      elif [ "$RELOAD" = 1 ]; then
        systemctl reload "php${V}-fpm" && say "  reload php${V}-fpm : OK (pools projet ; www flippe au prochain restart)"
      else
        say "  (ni reload ni restart — --reload (pools projet, sans coupure) ou --restart (état propre www))"
      fi
    else
      say "  php-fpm$V -t : ÉCHEC -> restauration du backup"
      sed 's/^/    /' /tmp/fpmtest.$V
      rm -rf "$PD"/*; tar xzf "$bk" -C "$PD"
      say "  restauré depuis $bk"
      return 1
    fi
  else
    say "  [DRY] puis: php-fpm$V -t (+ reload si --reload)"
  fi
}

neutralize_www() {
  local V="$1" VN="$2" www="$3" PD="/etc/php/$1/fpm/pool.d"
  if [ "$APPLY" = 1 ]; then
    [ -f "$PD/www.conf.orig" ] || { [ -f "$www" ] && cp "$www" "$PD/www.conf.orig"; }
    cat > "$www" <<EOF
[www-$VN]

include = $PD/default.conf.inc
include = $PD/common.conf.inc
EOF
    say "  www.conf : neutralisé -> [www-$VN] + includes (orig sauvé)"
  else
    say "  [DRY] www.conf : -> [www-$VN] + include default + include common (orig sauvé)"
  fi
}

rc=0
for V in "${TARGETS[@]}"; do
  [ "$V" = "$REF_VER" ] && { hr "PHP $V"; say "  (référence, skip)"; continue; }
  migrate_one "$V" || rc=1
done
exit $rc
