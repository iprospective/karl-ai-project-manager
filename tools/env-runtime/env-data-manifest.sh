#!/bin/bash
# env-data-manifest.sh — LA déclaration des dossiers de données d'une appli, résolue (RM3419).
#
# Bibliothèque sourçable (pas un exécutable) : les scripts qui touchent aux données s'y branchent
# au lieu de recopier des listes. Un seul endroit dit OÙ vivent les données d'un type d'appli.
#
#   . env-data-manifest.sh
#   manifeste_type <type> <racine_du_site>     # → lignes "<nom>|<chemin>"
#   detecte_type   <racine_du_site>            # → presta | dolibarr | wordpress | ""
#
# Deux niveaux, le second l'emporte par <nom> (et `<nom>|-` désactive une entrée) :
#   1. générique, à côté de cette bibliothèque : `<type>-data.map` — le CŒUR de l'appli ;
#      une variante par version majeure est possible : `<type>-data-<majeure>.map` ;
#   2. le SITE : `<racine>/.<type>-data.map` (versionné avec le code, donc présent dans chaque
#      worktree ET en prod) ou, à défaut, `<racine>/.mmi-pm/<type>-data.map`. C'est là que vivent
#      les dossiers de données des MODULES/extensions, propres à chaque site.
#
# Pourquoi versionner la surcharge DANS le dépôt du code : un env est un `git worktree`, il n'a
# pas de `.mmi-pm` (celui-ci est à la racine du workspace) — une déclaration posée là ne serait
# vue par aucun env (constaté RM3419).
#
# Les applis ne se valent pas : Dolibarr range tout sous `documents/`, une ligne suffit ;
# PrestaShop éparpille ses données dans une quinzaine de dossiers du cœur, plus ceux de chaque
# module. C'est précisément pourquoi la liste est une DONNÉE et pas du code.

_manifeste_dir() { cd "$(dirname "${BASH_SOURCE[0]}")" && pwd; }

detecte_type() {
  local r="${1:-.}"
  if   [ -f "$r/app/AppKernel.php" ] || [ -f "$r/config/defines.inc.php" ]; then printf 'presta'
  elif [ -f "$r/htdocs/conf/conf.php" ] || [ -f "$r/htdocs/master.inc.php" ]; then printf 'dolibarr'
  elif [ -f "$r/wp-config.php" ] || [ -f "$r/wp-load.php" ]; then printf 'wordpress'
  fi
}

version_majeure() {
  local r="${1:-.}" t="${2:-}" v=""
  case "$t" in
    presta)
      [ -f "$r/app/AppKernel.php" ] && v=$(grep -oE "const VERSION *= *'[0-9.]+'" "$r/app/AppKernel.php" 2>/dev/null | grep -oE '[0-9.]+' | head -1)
      [ -n "$v" ] || { [ -f "$r/config/settings.inc.php" ] && v=$(grep -oE "_PS_VERSION_', *'[0-9.]+'" "$r/config/settings.inc.php" 2>/dev/null | grep -oE '[0-9.]+' | head -1); } ;;
    dolibarr)
      [ -f "$r/htdocs/filefunc.inc.php" ] && v=$(grep -oE "DOL_VERSION', *'[0-9.]+'" "$r/htdocs/filefunc.inc.php" 2>/dev/null | grep -oE '[0-9.]+' | head -1) ;;
    wordpress)
      [ -f "$r/wp-includes/version.php" ] && v=$(grep -oE "wp_version = '[0-9.]+'" "$r/wp-includes/version.php" 2>/dev/null | grep -oE '[0-9.]+' | head -1) ;;
  esac
  printf '%s' "$v"
}

manifeste_fichiers() {
  local type="$1" racine="$2" dir maj
  dir="$(_manifeste_dir)"
  maj="$(version_majeure "$racine" "$type")"; maj="${maj%%.*}"
  if [ -n "$maj" ] && [ -f "$dir/$type-data-$maj.map" ]; then printf '%s\n' "$dir/$type-data-$maj.map"
  elif [ -f "$dir/$type-data.map" ]; then printf '%s\n' "$dir/$type-data.map"
  fi
  if   [ -f "$racine/.$type-data.map" ];          then printf '%s\n' "$racine/.$type-data.map"
  elif [ -f "$racine/.mmi-pm/$type-data.map" ];   then printf '%s\n' "$racine/.mmi-pm/$type-data.map"
  fi
}

# manifeste_type <type> <racine> → "<nom>|<chemin>" dédupliqué par nom, surcharge du site gagnante
manifeste_type() {
  local type="$1" racine="$2" f
  while IFS= read -r f; do [ -n "$f" ] && cat "$f"; done < <(manifeste_fichiers "$type" "$racine") \
    | sed 's/#.*$//' | tr -d ' \t' | grep -E '^[A-Za-z0-9_.-]+\|' \
    | awk -F'|' '{ m[$1]=$2; if (!(($1) in seen)) { o[++n]=$1; seen[$1]=1 } }
                  END { for (i=1;i<=n;i++) if (m[o[i]]!="-") print o[i]"|"m[o[i]] }'
}
