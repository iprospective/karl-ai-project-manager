#!/usr/bin/env bash
#
# Dépose les overrides « domaine-agnostique » dans un worktree PrestaShop de
# dev/recette (RM2813).
#
# Un env servi sur un domaine alternatif tout en partageant la base d'un autre
# environnement subit la redirection que PrestaShop force vers le domaine de
# `ps_shop_url` : 301 en front, 302 vers AdminLogin en back-office. Quatre
# overrides l'en empêchent — c'est le motif éprouvé chez pisceen :
#
#   Shop.php            résolution : ne pas rediriger pour un hôte inconnu
#   ShopUrl.php         Tools::getShopDomain() renvoie l'hôte courant
#   Link.php            getAdminBaseLink() — le back-office, qui relit un shop
#                       rechargé depuis la base pendant le cycle du kernel
#   AdminController.php force shop->domain à chaque init de contrôleur admin
#
# Les trois premiers ne suffisent pas : sans Link.php, le back-office redirige.
#
# Point délicat : plusieurs projets ont DÉJÀ leur propre `override/classes/Link.php`
# suivi par git (Calicote y a `getCategoryLink`). Le remplacer effacerait du code
# projet. On fusionne alors les deux méthodes dans le fichier existant et on masque
# la modification à git par `--skip-worktree`.
#
# Idempotent : re-jouable sans dégât.
#
# Usage : presta-dev-overrides.sh [worktree]   (défaut : cwd)

set -euo pipefail

WT="${1:-$PWD}"
cd "$WT" || { echo "presta-dev-overrides: worktree introuvable : $WT" >&2; exit 1; }

# Assets : la copie versionnée du cœur PM d'abord, le skill du profil en repli.
SELF_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
for cand in "$SELF_DIR/presta-dev-overrides" "$HOME/.claude/skills/mmi-presta-dev-vhost/assets"; do
    [ -f "$cand/Shop.php" ] && ASSETS="$cand" && break
done
if [ -z "${ASSETS:-}" ]; then
    echo "presta-dev-overrides: assets introuvables — env laissé sans overrides" >&2
    exit 0                      # ne jamais faire échouer la création d'env pour ça
fi

EXCL=$(git rev-parse --git-path info/exclude 2>/dev/null || echo /dev/null)
exclude() { grep -qxF "$1" "$EXCL" 2>/dev/null || echo "$1" >> "$EXCL"; }

# 1. les trois overrides sans conflit connu — déposés tels quels
mkdir -p override/classes/shop override/classes/controller
for pair in "Shop.php:override/classes/shop" "ShopUrl.php:override/classes/shop" \
            "AdminController.php:override/classes/controller"; do
    src=${pair%%:*}; dir=${pair#*:}
    if git ls-files --error-unmatch "$dir/$src" >/dev/null 2>&1; then
        echo "presta-dev-overrides: $dir/$src est suivi par git — laissé intact, à fusionner à la main" >&2
        continue
    fi
    cp -a "$ASSETS/$src" "$dir/$src"
    exclude "$dir/$src"
done

# 2. Link.php — fusion si le projet a déjà le sien
LINK=override/classes/Link.php
if [ -f "$LINK" ] && grep -q 'rmDevAltHostLink' "$LINK"; then
    :                                       # déjà fusionné
elif [ -f "$LINK" ]; then
    python3 - "$ASSETS/Link.php" "$LINK" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
hack, cur = open(src).read(), open(dst).read()
body = hack[hack.index('    public function getAdminBaseLink'):hack.rindex('}')].rstrip()
note = ("\n\n    // >>> override « domaine-agnostique » DEV/TEST (RM2813)\n"
        "    // Fusionné ici parce que ce projet a DÉJÀ son propre override Link : le\n"
        "    // fichier de référence l'écraserait. Modification LOCALE au worktree,\n"
        "    // masquée à git par --skip-worktree. NE JAMAIS COMMITER NI DÉPLOYER.\n")
end = cur.rindex('}')
open(dst, 'w').write(cur[:end].rstrip() + note + body + "\n    // <<< fin override domaine-agnostique\n}\n")
PY
    git update-index --skip-worktree "$LINK" 2>/dev/null || true
else
    cp -a "$ASSETS/Link.php" "$LINK"
    exclude "$LINK"
fi

# 3. le cache garde l'index des classes : sans purge, les overrides restent ignorés
rm -rf var/cache/prod/* var/cache/dev/* 2>/dev/null || true

echo "✓ overrides domaine-agnostique en place ($(basename "$ASSETS"))"
