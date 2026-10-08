#!/bin/bash
# env-link-data.sh — les DONNÉES d'un env de dev pointent vers un env socle, au lieu d'y être
# recopiées (RM3419, pour RM3218 ; brique de RM2577). Vaut pour TOUTE appli déclarée.
#
#   env-link-data.sh --env <racine> --socle <racine> [--type presta|dolibarr|wordpress]
#                    [--apply] [--scan "<dossiers>"] [--quiet]
#
#   env-link-data.sh --env envs/site-rm42 --socle envs/site-dev              # simulation
#   env-link-data.sh --env envs/site-rm42 --socle envs/site-dev --apply
#
# POURQUOI. Un `git worktree` ne contient que les fichiers SUIVIS. Tout ce qu'un utilisateur a
# déposé — images produit, pièces jointes, bannières de modules, documents — vit hors dépôt : un
# env neuf naît sans, et le recopier duplique des centaines de Mo qui divergent ensuite. Le socle
# est la source unique.
#
# CE QUI EST GÉNÉRIQUE, ET CE QUI NE L'EST PAS. La liste des dossiers de données est une DONNÉE,
# pas du code : elle vit dans `<type>-data.map` (+ la surcharge du site), résolue par
# `env-data-manifest.sh`. Les applis ne se ressemblent pas — Dolibarr range tout sous
# `documents/` (une ligne), PrestaShop éparpille une quinzaine de dossiers du cœur plus ceux de
# chaque module. Ce script ne connaît aucune de ces listes.
#
# DEUX FAÇONS DE BRANCHER, choisies par dossier :
#   · dossier ENTIER → un lien, quand le dossier est absent ou vide ici et qu'aucun fichier du
#     dépôt n'y vit ;
#   · sinon FICHIER PAR FICHIER, pour les seuls fichiers non suivis. Mesuré sur un env réel
#     (RM3218) : sur 36 dossiers d'assets PrestaShop, 5 seulement sont entièrement non suivis ;
#     les autres mélangent fichiers du dépôt et fichiers déposés. Lier le dossier ferait voir à
#     git la suppression des fichiers suivis, et le prochain `git checkout` entrerait en conflit.
#
# `--scan "<dossiers>"` ratisse en plus les IMAGES non déclarées de ces dossiers (défaut pour
# PrestaShop : `modules themes`, dont la longue traîne d'assets de modules n'est jamais
# exhaustivement déclarée). `--scan ""` le désactive.
#
# CE QU'IL NE FAIT JAMAIS
#   · toucher un fichier suivi par git (ni le lier, ni l'effacer) ;
#   · lier un CATALOGUE DE TRADUCTION : le Finder de Symfony ne suit pas les liens symboliques,
#     un catalogue lié rend le front en ANGLAIS alors que les fichiers sont là (RM3410) — le scan
#     ne porte donc que sur une liste blanche d'extensions d'images ;
#   · entrer dans un dossier déjà emprunté en entier (c'est déjà un lien) ;
#   · écrire quoi que ce soit sans `--apply`.
#
# Idempotent. Les liens posés sont ABSOLUS (un env et son socle ne sont pas à une profondeur fixe
# l'un de l'autre) et ajoutés à `.git/info/exclude`.
set -u

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
. "$SELF_DIR/env-data-manifest.sh"

ENV_ROOT=""; SOCLE=""; TYPE=""; APPLY=0; QUIET=0; SCAN=""; SCAN_SET=0
IMG_EXT=(jpg jpeg png webp gif svg ico avif)

while [ $# -gt 0 ]; do
  case "$1" in
    --env)   ENV_ROOT="${2:?--env attend un chemin}"; shift 2 ;;
    --socle) SOCLE="${2:?--socle attend un chemin}"; shift 2 ;;
    --type)  TYPE="${2:?--type attend presta|dolibarr|wordpress}"; shift 2 ;;
    --scan)  SCAN="${2-}"; SCAN_SET=1; shift 2 ;;
    --apply) APPLY=1; shift ;;
    --quiet) QUIET=1; shift ;;
    -h|--help) sed -n '2,45p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "ERREUR : option inconnue : $1" >&2; exit 2 ;;
  esac
done
[ -n "$ENV_ROOT" ] && [ -n "$SOCLE" ] || { echo "ERREUR : --env et --socle sont requis (--help)" >&2; exit 2; }
ENV_ROOT="$(cd "$ENV_ROOT" 2>/dev/null && pwd)" || { echo "ERREUR : env introuvable" >&2; exit 2; }
SOCLE="$(cd "$SOCLE" 2>/dev/null && pwd)"       || { echo "ERREUR : socle introuvable" >&2; exit 2; }
[ "$ENV_ROOT" = "$SOCLE" ] && { echo "ERREUR : l'env et le socle sont le même dossier" >&2; exit 2; }

[ -n "$TYPE" ] || TYPE="$(detecte_type "$ENV_ROOT")"
[ -n "$TYPE" ] || { echo "ERREUR : type d'appli indétectable sous $ENV_ROOT — passer --type" >&2; exit 2; }
[ "$(detecte_type "$SOCLE")" = "$TYPE" ] || [ -n "${TYPE_FORCE:-}" ] || {
  echo "ERREUR : le socle n'est pas du même type ($TYPE attendu) — socle=$(detecte_type "$SOCLE")" >&2; exit 2; }

MANIFESTES="$(manifeste_fichiers "$TYPE" "$ENV_ROOT" | tr '\n' ' ')"
[ -n "${MANIFESTES// /}" ] || { echo "ERREUR : aucun manifeste pour le type $TYPE" >&2; exit 2; }
# Longue traîne : par défaut on ne ratisse que PrestaShop, dont les modules portent des images
# jamais toutes déclarées. Les autres applis s'en tiennent au manifeste.
if [ "$SCAN_SET" = 0 ]; then
  case "$TYPE" in presta) SCAN="modules themes" ;; *) SCAN="" ;; esac
fi

cd "$ENV_ROOT" || exit 2
EXCL="$(git rev-parse --git-path info/exclude 2>/dev/null)" || EXCL=""
[ -n "$EXCL" ] || EXCL=/dev/null
# L'index git est lu UNE FOIS : un `git ls-files` par fichier coûtait des dizaines de minutes sur
# un PrestaShop (≈ 40 000 fichiers suivis, 8 000 images rien que dans img/p). On charge l'index en
# mémoire, plus les dossiers qui portent au moins un fichier suivi — deux tests O(1) ensuite.
declare -A _SUIVI=() _DIR_SUIVI=()
while IFS= read -r -d '' p; do
  _SUIVI["$p"]=1
  d="${p%/*}"
  while [ -n "$d" ] && [ "$d" != "$p" ]; do
    [ -n "${_DIR_SUIVI[$d]:-}" ] && break
    _DIR_SUIVI["$d"]=1
    [ "${d%/*}" = "$d" ] && break
    d="${d%/*}"
  done
done < <(git ls-files -z 2>/dev/null)
suivi()    { [ -n "${_SUIVI[$1]:-}" ]; }
a_suivis() { [ -n "${_DIR_SUIVI[$1]:-}" ]; }
exclure() { grep -qxF "$1" "$EXCL" 2>/dev/null || echo "$1" >> "$EXCL"; }
dit()     { [ "$QUIET" = 1 ] || printf '%s\n' "$*"; }

# Un ANCÊTRE déjà lié veut dire « ce sous-arbre est emprunté au socle » : il ne faut surtout pas
# descendre dedans. Sans cette garde, un chemin comme `img/p/1/2.jpg` traversé à travers le lien
# `img` → socle existe, n'est pas suivi par git… et on écrirait un lien PAR-DESSUS LE FICHIER DU
# SOCLE. C'est la façon la plus discrète de corrompre la source unique (trouvé en mesurant, RM3419).
ancetre_lien() {
  local d="${1%/*}"
  while [ -n "$d" ] && [ "$d" != "$1" ]; do
    [ -L "$d" ] && return 0
    [ "${d%/*}" = "$d" ] && break
    d="${d%/*}"
  done
  return 1
}

lie_fichier() {   # <chemin relatif> → 0 si lié (ou le serait), 1 si laissé
  local f="$1"
  [ -L "$f" ] && return 1
  ancetre_lien "$f" && return 1
  [ -e "$f" ] && suivi "$f" && return 1
  if [ "$APPLY" = 1 ]; then
    mkdir -p "$(dirname "$f")"; rm -f "$f"
    ln -s "$SOCLE/$f" "$f"; exclure "$f"
  fi
  return 0
}

# ── 1. les dossiers DÉCLARÉS : le plus gros lien possible, en descendant l'arbre ──
#
# Un dossier de données contient souvent quelques fichiers du DÉPÔT au milieu de milliers de
# fichiers déposés : `img/p` porte les images par défaut de PrestaShop (suivies) et les 8 000
# images produit (non suivies). Tomber droit au fichier y poserait 38 000 liens (mesuré). On descend
# donc : un dossier sans aucun fichier suivi est lié ENTIER ; sinon on recurse dans ses
# sous-dossiers, et on ne traite fichier par fichier que les feuilles réellement mixtes.
d_lies=0; d_fichiers=0; d_descendus=0; d_empruntes=0

lie_arbre() {
  local chemin="$1" e
  [ -d "$SOCLE/$chemin" ] || return 0
  if [ -L "$chemin" ] || ancetre_lien "$chemin"; then d_empruntes=$((d_empruntes+1)); return 0; fi
  if ! a_suivis "$chemin" && { [ ! -d "$chemin" ] || [ -z "$(ls -A "$chemin" 2>/dev/null | grep -v '^index.php$' | head -1)" ]; }; then
    if [ "$APPLY" = 1 ]; then
      mkdir -p "$(dirname "$chemin")"; rm -rf "$chemin"
      ln -s "$SOCLE/$chemin" "$chemin"; exclure "$chemin"
    fi
    d_lies=$((d_lies+1)); return 0                            # dossier entier : un seul lien
  fi
  d_descendus=$((d_descendus+1))
  while IFS= read -r e; do
    [ -n "$e" ] || continue
    if [ -d "$SOCLE/$chemin/$e" ]; then
      lie_arbre "$chemin/$e"
    else
      lie_fichier "$chemin/$e" && d_fichiers=$((d_fichiers+1))
    fi
  done < <(ls -A "$SOCLE/$chemin" 2>/dev/null)
}

while IFS='|' read -r nom chemin; do
  [ -n "${chemin:-}" ] || continue
  lie_arbre "$chemin"
done < <(manifeste_type "$TYPE" "$ENV_ROOT")

# ── 2. la longue traîne : images non déclarées des dossiers de --scan ─────────
s_lies=0; s_suivis=0; s_empruntes=0; s_deja=0
if [ -n "${SCAN// /}" ]; then
  expr=(); for e in "${IMG_EXT[@]}"; do expr+=(-o -name "*.$e"); done
  for d in $SCAN; do
    [ -d "$SOCLE/$d" ] || continue
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      if ancetre_lien "$f"; then s_empruntes=$((s_empruntes+1)); continue; fi
      if [ -L "$f" ];      then s_deja=$((s_deja+1)); continue; fi
      if [ -e "$f" ] && suivi "$f"; then s_suivis=$((s_suivis+1)); continue; fi
      lie_fichier "$f" && s_lies=$((s_lies+1))
    done < <(cd "$SOCLE" && find "$d" -type f \( "${expr[@]:1}" \) 2>/dev/null)
  done
fi

V="$(version_majeure "$ENV_ROOT" "$TYPE")"
dit "env-link-data : $(basename "$ENV_ROOT") → $(basename "$SOCLE")  (type $TYPE${V:+ $V})"
dit "  manifeste(s) : ${MANIFESTES% }"
dit "  déclarés : $d_lies dossier(s) lié(s) entier(s) · $d_fichiers fichier(s) lié(s) dans une feuille mixte · $d_descendus dossier(s) parcouru(s) (ils portent des fichiers du dépôt) · $d_empruntes déjà emprunté(s)"
if [ -n "${SCAN// /}" ]; then
  dit "  scan ($SCAN) : $s_lies image(s) liée(s) · $s_suivis suivie(s) par git (intouchées) · $s_empruntes dans un dossier emprunté · $s_deja déjà liée(s)"
fi
[ "$APPLY" = 1 ] || dit "  (simulation — relancer avec --apply)"
