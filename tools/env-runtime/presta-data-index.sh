#!/bin/bash
# presta-data-index — le dossier `data/` d'un PrestaShop : un lien symbolique RELATIF
# vers chaque dossier de données du site (RM3401, pour RM3186).
#
# CE SCRIPT NE DÉPLACE RIEN. Il ne fait que trois choses : créer des liens dans `data/`,
# y poser un `.htaccess` qui refuse tout accès HTTP, et dire ce qui ne va pas. Aucune
# commande de déplacement ni de suppression n'y figure — un test le vérifie sur le
# source, en ignorant les commentaires, et recompte les données après exécution.
# Les données restent là où PrestaShop les écrit ; `data/` est un INDEX, pas un magasin.
#
# Pourquoi des liens DANS data/ et pas l'inverse : un lien posé dans l'arbre PrestaShop
# disparaît avec le dossier qui le porte dès qu'une mise à jour du cœur ou d'un module
# le supprime et le recrée. Ici, aucun lien n'est posé dans l'arbre : ils sont tous dans
# `data/` et pointent vers des chemins stables, définis par PrestaShop lui-même. Une
# mise à jour ne peut pas les casser.
#
# Les liens sont RELATIFS (`data/product-img` → `../img/p`) : identiques dans chaque
# worktree et en prod, donc commitables tels quels. Une fois commités, git les reproduit
# partout et ce script n'a plus à tourner — il reste pour `--check`.
#
# Usage :
#   presta-data-index.sh --list   [<racine>]   le manifeste résolu, rien d'autre
#   presta-data-index.sh --check  [<racine>]   contrôle (exit 1 si anomalie), n'écrit rien
#   presta-data-index.sh --ensure [<racine>]   crée/répare les liens + le .htaccess
#   presta-data-index.sh --ensure --dry-run [<racine>]
#
# <racine> : la racine du site (défaut : le dossier courant). Le manifeste générique est
# `presta-data.map`, à côté de ce script ; la surcharge du projet est
# `<racine>/.mmi-pm/presta-data.map` (elle ajoute les dossiers de données des modules,
# qui sont propres à chaque site).
set -uo pipefail

SELF_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MAP_BASE="$SELF_DIR/presta-data.map"
MODE=""
DRY=0
ROOT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --list|--check|--ensure) MODE="${1#--}" ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,34p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "ERREUR : option inconnue $1" >&2; exit 2 ;;
    *) ROOT="$1" ;;
  esac
  shift
done
[ -n "$MODE" ] || { echo "ERREUR : --list, --check ou --ensure attendu" >&2; exit 2; }
ROOT=${ROOT:-.}
[ -d "$ROOT" ] || { echo "ERREUR : racine introuvable : $ROOT" >&2; exit 2; }
ROOT=$(cd "$ROOT" && pwd)

# Un PrestaShop, vraiment ? Sans ce garde-fou, une racine mal passée créerait un `data/`
# de liens pendants dans n'importe quel dossier.
if [ "$MODE" != "list" ] && [ ! -f "$ROOT/config/defines.inc.php" ]; then
  echo "ERREUR : $ROOT ne ressemble pas à un PrestaShop (config/defines.inc.php absent)" >&2
  exit 2
fi

# ── manifeste ────────────────────────────────────────────────────────────────────
# Générique puis surcharge projet ; une même entrée vue deux fois garde la DERNIÈRE
# définition (le projet gagne), une cible `-` la retire. L'ordre de sortie suit la
# première apparition, pour que `--list` reste lisible et stable.
declare -A TARGET=()
NAMES=()

read_map() {
  local f="$1" line name target
  [ -f "$f" ] || return 0
  while IFS= read -r line; do
    line="${line%%#*}"
    line="$(echo "$line" | sed 's/[[:space:]]*$//; s/^[[:space:]]*//')"
    [ -n "$line" ] || continue
    case "$line" in *"|"*) ;; *) echo "⚠ $f : ligne ignorée (pas de « | ») : $line" >&2; continue ;; esac
    name="${line%%|*}"; target="${line#*|}"
    name="$(echo "$name" | sed 's/[[:space:]]*$//')"
    target="$(echo "$target" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    # Un nom peut porter UN sous-dossier (`modules/<module>`), mais jamais remonter :
    # `..` ou un chemin absolu ferait sortir le lien de data/, donc du site.
    case "$name" in
      /*|*..*) echo "⚠ $f : nom invalide (absolu ou remontant) : $name" >&2; continue ;;
      .|"") continue ;;
    esac
    if [ -z "${TARGET[$name]+x}" ]; then NAMES+=("$name"); fi
    TARGET[$name]="$target"
  done < "$f"
}

read_map "$MAP_BASE"
read_map "$ROOT/.mmi-pm/presta-data.map"

# ── sortie ───────────────────────────────────────────────────────────────────────
RC=0
PASS="✓"; WARN="⚠"; FAIL="✗"
n_ok=0; n_new=0; n_fix=0; n_miss=0; n_block=0

# Le lien relatif de `data/<nom>` vers <cible> : un `../` par segment de profondeur du
# nom, puis la cible. `data/x` → `../<cible>` ; `data/modules/x` → `../../<cible>`.
rel_to() {
  local name="$1" target="$2" up="../" d
  d=$(dirname "$name")
  if [ "$d" != "." ]; then
    local IFS=/; for _ in $d; do up="../$up"; done
  fi
  echo "${up}${target}"
}

HTACCESS_BODY='# Posé par presta-data-index (RM3401) — `data/` est un INDEX de liens vers les
# données du site, il ne doit JAMAIS être servi en HTTP : les liens y donnent accès à
# `upload/` et `download/`, que leur propre .htaccess protège.
<IfModule !mod_authz_core.c>
    Order deny,allow
    Deny from all
</IfModule>
<IfModule mod_authz_core.c>
    Require all denied
</IfModule>'

if [ "$MODE" = "list" ]; then
  for name in "${NAMES[@]}"; do
    [ "${TARGET[$name]}" = "-" ] && continue
    printf '%-26s → %s\n' "data/$name" "$(rel_to "$name" "${TARGET[$name]}")"
  done
  exit 0
fi

for name in "${NAMES[@]}"; do
  target="${TARGET[$name]}"
  [ "$target" = "-" ] && continue
  link="$ROOT/data/$name"
  want="$(rel_to "$name" "$target")"

  # La cible doit exister : on ne crée jamais un lien pendant, et on ne crée jamais le
  # dossier de données non plus — ce serait décider à la place de PrestaShop.
  if [ ! -d "$ROOT/$target" ]; then
    echo "  $WARN $name : cible absente ($target) — aucun lien créé"
    n_miss=$((n_miss + 1)); RC=1; continue
  fi

  if [ -L "$link" ]; then
    have="$(readlink "$link")"
    if [ "$have" = "$want" ]; then
      n_ok=$((n_ok + 1)); continue
    fi
    if [ "$MODE" = "check" ]; then
      echo "  $FAIL $name : pointe sur « $have », attendu « $want »"; RC=1; continue
    fi
    [ "$DRY" = 1 ] && { echo "  (dry-run) $name : « $have » → « $want »"; n_fix=$((n_fix + 1)); continue; }
    ln -sfn "$want" "$link" && { echo "  $PASS $name : relié à nouveau ($want)"; n_fix=$((n_fix + 1)); }
    continue
  fi

  # Quelque chose d'autre qu'un lien occupe la place : on s'ARRÊTE. Ne jamais supprimer
  # ni déplacer ce qu'on n'a pas posé — ce serait le seul geste destructeur possible ici.
  if [ -e "$link" ]; then
    echo "  $FAIL $name : « data/$name » existe et n'est pas un lien — rien n'est touché, à régler à la main"
    n_block=$((n_block + 1)); RC=1; continue
  fi

  if [ "$MODE" = "check" ]; then
    echo "  $FAIL $name : lien absent (attendu $want)"; RC=1; continue
  fi
  [ "$DRY" = 1 ] && { echo "  (dry-run) $name : lien à créer → $want"; n_new=$((n_new + 1)); continue; }
  mkdir -p "$(dirname "$link")" || { RC=1; continue; }
  ln -s "$want" "$link" && { echo "  $PASS $name → $want"; n_new=$((n_new + 1)); }
done

# ── .htaccess ────────────────────────────────────────────────────────────────────
HT="$ROOT/data/.htaccess"
if [ "$MODE" = "check" ]; then
  if [ ! -f "$HT" ]; then
    echo "  $FAIL data/.htaccess absent — data/ serait servi en HTTP"; RC=1
  elif ! grep -q "Require all denied" "$HT"; then
    echo "  $FAIL data/.htaccess ne refuse pas tout"; RC=1
  fi
elif [ "$DRY" = 1 ]; then
  [ -f "$HT" ] || echo "  (dry-run) data/.htaccess à poser"
elif [ ! -f "$HT" ]; then
  mkdir -p "$ROOT/data" && printf '%s\n' "$HTACCESS_BODY" > "$HT" \
    && echo "  $PASS data/.htaccess posé (refuse tout)"
elif ! grep -q "Require all denied" "$HT"; then
  echo "  $WARN data/.htaccess existe mais ne refuse pas tout — laissé tel quel, à vérifier"
  RC=1
fi

if [ "$MODE" = "check" ]; then
  [ "$RC" = 0 ] && echo "$PASS data/ conforme ($n_ok lien(s))" || echo "$FAIL data/ non conforme"
else
  echo "$PASS data/ : $n_ok déjà bon(s), $n_new créé(s), $n_fix réparé(s)$([ "$n_miss" != 0 ] && echo ", $n_miss cible(s) absente(s)")$([ "$n_block" != 0 ] && echo ", $n_block bloqué(s)")"
fi
exit $RC
