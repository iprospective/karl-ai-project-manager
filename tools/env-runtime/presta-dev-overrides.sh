#!/usr/bin/env bash
# presta-dev-overrides.sh — dépose les overrides « domaine-agnostique » DEV-ONLY
# dans un worktree PrestaShop. RM2812.
#
# Sert un worktree sur un domaine dédié tout en partageant la base d'un autre
# environnement. Sans ces overrides, PrestaShop renvoie un 301 vers le domaine
# inscrit dans `ps_shop_url` — c'est-à-dire vers l'environnement principal, voire
# vers la production.
#
# QUATRE volets (RM2687) :
#   Shop.php + ShopUrl.php  le FRONT — résolution du shop et liens ;
#   Link.php                le BACK-OFFICE — pendant $kernel->handle(), l'objet
#                           shop est rechargé depuis la base, ce qui écrase le
#                           domaine forcé par Shop::initialize() ;
#   AdminController.php     réaligne shop->domain dans le BO et masque le
#                           bandeau ps_accounts, sans objet sur un env de test.
#
# ⚠ Rien de tout cela ne doit être commité ni déployé. Les fichiers déposés sont
# ajoutés à .git/info/exclude ; ceux qui sont INJECTÉS dans un override existant
# sont passés en skip-worktree.
#
# Le point délicat (RM2811) : un projet peut avoir un override MÉTIER sur la même
# classe. calicote a un `override/classes/Link.php` tracké (redirection « Box »)
# et, depuis RM2857, un `override/classes/controller/AdminController.php` tracké
# lui aussi. Un `cp` les écraserait, et `info/exclude` ne protège rien puisqu'il
# ne s'applique qu'aux fichiers NON suivis : la perte apparaîtrait comme une
# simple modification, à un `git add` malheureux près.
#
# D'où trois comportements, et jamais d'écrasement :
#   cible absente ou non suivie  -> copie de l'asset ;
#   cible suivie, sans collision -> injection d'un bloc marqué dans la classe ;
#   cible suivie, avec collision -> REFUS, sans rien toucher.
#
# Usage : presta-dev-overrides.sh <worktree> [--on <user@host>]
#
# `--on` (RM3196) : tous les environnements ne vivent pas sur la machine qui porte
# l'outillage — ceux de `dercya-www` sont distants. Le script se transporte alors
# lui-même (avec ses assets) et s'exécute là-bas sur le chemin donné.
#
# La logique de dépôt, elle, ne connaît PAS le réseau : à distance comme en local
# elle ne voit qu'un chemin local, sur l'hôte où elle tourne. Le transport
# s'ajoute autour, il ne se mélange pas au reste — c'est ce qui permet de garder
# un seul point d'entrée sans que les garde-fous aient deux comportements.
set -uo pipefail

REMOTE=""
WT=""
while [ $# -gt 0 ]; do
    case "$1" in
        --on)
            REMOTE="${2:-}"
            [ -n "$REMOTE" ] || { echo "presta-dev-overrides: --on attend <user@host>" >&2; exit 2; }
            shift 2
            ;;
        --on=*)
            REMOTE="${1#--on=}"
            shift
            ;;
        -*)
            echo "presta-dev-overrides: option inconnue : $1" >&2
            exit 2
            ;;
        *)
            [ -n "$WT" ] && { echo "presta-dev-overrides: un seul chemin attendu" >&2; exit 2; }
            WT="$1"
            shift
            ;;
    esac
done
WT="${WT:-.}"

MARK_OPEN="// >>> presta-dev-overrides (RM2812) — DEV-ONLY, ne pas commiter"
MARK_CLOSE="// <<< presta-dev-overrides"

# Assets : repo PM d'abord (versionnés), skill déployé ensuite. Sans l'un des
# deux on s'arrête net — un worktree servi sans ces overrides renverrait des 301
# vers la production, ce qui est pire qu'un environnement manquant.
ASSETS=""
for cand in \
    "$(dirname "$(readlink -f "$0")")/presta-dev-assets" \
    "$HOME/.claude/skills/mmi-presta-dev-vhost/assets"
do
    if [ -f "$cand/Shop.php" ]; then ASSETS="$cand"; break; fi
done
if [ -z "$ASSETS" ]; then
    echo "presta-dev-overrides: assets introuvables (repo PM ni skill déployé) —" \
         "un worktree sans ces overrides redirigerait vers la production." >&2
    exit 1
fi

# ─── relais distant (RM3196) ────────────────────────────────────────────────
#
# Script et assets partent dans UN seul flux tar sur stdin de ssh, qui extrait
# dans un dossier temporaire, exécute, puis nettoie par un trap. Rien ne reste
# sur l'hôte distant : une copie laissée en place vieillirait en silence et on
# déposerait un jour des overrides périmés sans s'en apercevoir.
if [ -n "$REMOTE" ]; then
    command -v ssh >/dev/null 2>&1 || {
        echo "presta-dev-overrides: ssh introuvable, --on impossible" >&2; exit 2; }
    command -v tar >/dev/null 2>&1 || {
        echo "presta-dev-overrides: tar introuvable, --on impossible" >&2; exit 2; }

    SELF="$(readlink -f "$0")"
    SELF_NAME="$(basename "$SELF")"
    ASSETS_NAME="$(basename "$ASSETS")"

    # Le chemin distant est cité une fois pour le shell distant ; le reste du
    # script embarqué est en quotes simples, donc rien d'autre n'est interprété
    # ici — pas d'échappement en cascade à relire dans six mois.
    REMOTE_WT="$(printf '%q' "$WT")"

    echo "presta-dev-overrides → $REMOTE:$WT"

    tar -C "$(dirname "$SELF")" -cf - "$SELF_NAME" \
        -C "$(dirname "$ASSETS")" "$ASSETS_NAME" \
    | ssh "$REMOTE" "
        set -eu
        d=\$(mktemp -d) || exit 2
        trap 'rm -rf \"\$d\"' EXIT
        tar -C \"\$d\" -xf -
        [ -d \"\$d/$ASSETS_NAME\" ] || { echo 'presta-dev-overrides: assets non transmis' >&2; exit 2; }
        chmod +x \"\$d/$SELF_NAME\"
        \"\$d/$SELF_NAME\" $REMOTE_WT
    "
    exit $?
fi

cd "$WT" || { echo "presta-dev-overrides: worktree introuvable : $WT" >&2; exit 2; }

EXCL="$(git rev-parse --git-path info/exclude 2>/dev/null)" || {
    echo "presta-dev-overrides: pas un dépôt git : $WT" >&2; exit 2; }

exclude_once() {
    grep -qxF "$1" "$EXCL" 2>/dev/null || echo "$1" >> "$EXCL"
}

is_tracked() {
    git ls-files --error-unmatch -- "$1" >/dev/null 2>&1
}

# Noms de méthodes et de constantes définis par un fichier de classe.
members_of() {
    grep -oE '(function|const)[[:space:]]+&?[A-Za-z_][A-Za-z0-9_]*' "$1" \
        | awk '{print $2}' | sed 's/^&//' | sort -u
}

# Corps de la classe : de la première accolade ouvrante après `class ...`
# jusqu'à la dernière accolade fermante du fichier, exclues.
class_body() {
    awk '
        !started && /(^|[[:space:]])class[[:space:]]/ { started = 1 }
        started && !open && /\{/ { open = 1; sub(/^[^{]*\{/, ""); if ($0 ~ /^[[:space:]]*$/) next }
        open { print }
    ' "$1" | awk '
        { lines[NR] = $0 }
        END {
            last = 0
            for (i = NR; i >= 1; i--) { if (lines[i] ~ /\}/) { last = i; break } }
            for (i = 1; i < last; i++) print lines[i]
        }'
}

deposit() {
    local asset="$1" target="$2" label="$3"
    local src="$ASSETS/$asset"

    [ -f "$src" ] || { echo "presta-dev-overrides: asset manquant : $src" >&2; return 1; }
    mkdir -p "$(dirname "$target")"

    # --- cible libre : copie pure et simple -------------------------------
    if [ ! -f "$target" ] || ! is_tracked "$target"; then
        cp -a "$src" "$target"
        exclude_once "$target"
        echo "  ✓ $label : déposé ($target)"
        return 0
    fi

    # --- cible suivie : override métier, on ne l'écrase JAMAIS ------------
    if grep -qF "$MARK_OPEN" "$target"; then
        echo "  = $label : bloc dev déjà injecté dans l'override métier"
        git update-index --skip-worktree -- "$target" 2>/dev/null || true
        return 0
    fi

    local collisions
    collisions="$(comm -12 <(members_of "$src") <(members_of "$target") | tr '\n' ' ')"
    if [ -n "${collisions// /}" ]; then
        echo "presta-dev-overrides: REFUS sur $target" >&2
        echo "  l'override métier définit déjà : ${collisions}" >&2
        echo "  PrestaShop n'admet qu'un override par classe : fusionner à la main," >&2
        echo "  puis marquer le bloc avec « $MARK_OPEN »." >&2
        echo "  Rien n'a été modifié." >&2
        return 1
    fi

    local bodyfile tmp lastline
    bodyfile="$(mktemp)"; tmp="$(mktemp)"
    class_body "$src" > "$bodyfile"
    if [ ! -s "$bodyfile" ]; then
        rm -f "$bodyfile" "$tmp"
        echo "presta-dev-overrides: corps de classe vide extrait de $src — rien modifié" >&2
        return 1
    fi

    # Ligne de la dernière accolade fermante seule sur sa ligne = fin de classe.
    lastline="$(awk '/^[[:space:]]*\}[[:space:]]*$/ { n = NR } END { print n + 0 }' "$target")"
    if [ "${lastline:-0}" -le 1 ]; then
        rm -f "$bodyfile" "$tmp"
        echo "presta-dev-overrides: fin de classe introuvable dans $target — rien modifié" >&2
        return 1
    fi

    # Assemblage par découpage : aucune interpolation du code PHP dans awk, dont
    # le `-v` interprète les séquences d'échappement et corromprait le corps.
    {
        head -n "$((lastline - 1))" "$target"
        echo ""
        echo "    $MARK_OPEN"
        cat "$bodyfile"
        echo "    $MARK_CLOSE"
        tail -n +"$lastline" "$target"
    } > "$tmp"
    rm -f "$bodyfile"

    # Garde-fou : le résultat doit CONTENIR l'override métier, pas le remplacer.
    # C'est la seule vérification qui attrape une injection partiellement écrite —
    # un `php -l` passe très bien sur un fichier tronqué mais syntaxiquement clos.
    local perdus
    perdus="$(comm -23 <(members_of "$target") <(members_of "$tmp") | tr '\n' ' ')"
    if [ -n "${perdus// /}" ]; then
        rm -f "$tmp"
        echo "presta-dev-overrides: ABANDON sur $target" >&2
        echo "  l'injection aurait fait disparaître : ${perdus}" >&2
        echo "  rien n'a été modifié." >&2
        return 1
    fi
    if ! grep -qF "$MARK_OPEN" "$tmp"; then
        rm -f "$tmp"
        echo "presta-dev-overrides: bloc dev absent du résultat pour $target — rien modifié" >&2
        return 1
    fi
    if ! { php -l "$tmp" >/dev/null 2>&1 || php7.4 -l "$tmp" >/dev/null 2>&1; }; then
        rm -f "$tmp"
        echo "presta-dev-overrides: l'injection produirait un PHP invalide dans $target — rien modifié" >&2
        return 1
    fi

    cat "$tmp" > "$target"
    rm -f "$tmp"
    # skip-worktree : le fichier reste suivi, mais l'injection ne remonte pas
    # dans `git status` et ne peut donc pas être commitée par inadvertance.
    git update-index --skip-worktree -- "$target" 2>/dev/null || true
    echo "  ✓ $label : bloc dev injecté dans l'override métier ($target)"
}

echo "presta-dev-overrides ← $ASSETS"
rc=0
deposit Shop.php            override/classes/shop/Shop.php                  "Shop (front)"            || rc=1
deposit ShopUrl.php         override/classes/shop/ShopUrl.php               "ShopUrl (front)"         || rc=1
deposit Link.php            override/classes/Link.php                       "Link (back-office)"      || rc=1
deposit AdminController.php override/classes/controller/AdminController.php "AdminController (BO)"    || rc=1

exit $rc
