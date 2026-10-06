#!/bin/bash
# Tests RM3401 — `data/` : l'index de liens vers les données d'un PrestaShop.
#
# Ce que ces tests protègent, dans l'ordre d'importance :
#
#   * LE SCRIPT NE DÉPLACE RIEN. C'est la condition posée par le demandeur, et c'est
#     vérifié deux fois : sur le SOURCE (aucun mv/rm -rf/cp) et sur le COMPORTEMENT
#     (les données sont comptées avant et après — elles doivent être intactes) ;
#   * un vrai dossier déjà en place dans data/ n'est jamais écrasé : le script s'arrête ;
#   * les liens sont RELATIFS (sinon ils seraient faux dans chaque worktree et en prod) ;
#   * --ensure est idempotent, et --check n'écrit rien ;
#   * une cible absente ne donne pas un lien pendant ;
#   * le .htaccess refuse tout (data/ donne accès à upload/, protégé par le sien).
#
# Lancer : bash scripts/test_presta_data_index.sh
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT="$HERE/../tools/env-runtime/presta-data-index.sh"
fails=0

check() { if [ "$2" = 0 ]; then echo "✓ $1"; else echo "✗ $1"; fails=$((fails + 1)); fi; }
ok() { [ "$1" = "$2" ] && echo 0 || echo 1; }

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SITE="$TMP/site"
mkdir -p "$SITE/config" "$SITE/img/p/1" "$SITE/img/c" "$SITE/img/cms" "$SITE/img/m" \
         "$SITE/img/su" "$SITE/img/st" "$SITE/img/s" "$SITE/img/l" "$SITE/img/co" \
         "$SITE/img/os" "$SITE/img/genders" "$SITE/img/e" "$SITE/img/pr" \
         "$SITE/upload" "$SITE/download" "$SITE/.mmi-pm" "$SITE/modules/demo/img"
touch "$SITE/config/defines.inc.php"
echo "photo" > "$SITE/img/p/1/1.jpg"
echo "piece" > "$SITE/upload/abc.pdf"
echo "banniere" > "$SITE/modules/demo/img/b.jpg"
printf 'modules/demo|modules/demo/img\n' > "$SITE/.mmi-pm/presta-data.map"
# La surcharge versionnée AVEC le site (cas d'un worktree, qui n'a pas de .mmi-pm).
printf 'cms-img|-\nmodules/demo2|modules/demo/img\n' > "$SITE/.presta-data.map"

# empreinte des DONNÉES avant toute exécution
AVANT=$(find "$SITE/img" "$SITE/upload" "$SITE/download" "$SITE/modules" -type f | sort)

# — le source lui-même ne sait pas déplacer —
# Commentaires retirés : on cherche des COMMANDES, pas des mots dans une explication.
src=$(sed 's/[[:space:]]*#.*$//' "$SCRIPT")
check "le source ne contient aucun 'mv'"        "$(ok "$(grep -cE '(^|[^[:alnum:]_])mv ' <<<"$src")" 0)"
check "le source ne contient aucun 'rm -rf'"    "$(ok "$(grep -c 'rm -rf' <<<"$src")" 0)"
check "le source ne contient aucun 'cp '"       "$(ok "$(grep -cE '(^|[^[:alnum:]_])cp ' <<<"$src")" 0)"
check "le source ne contient aucun 'rsync'"     "$(ok "$(grep -c 'rsync' <<<"$src")" 0)"

# — refus d'une racine qui n'est pas un PrestaShop —
"$SCRIPT" --ensure "$TMP" >/dev/null 2>&1
check "une racine sans config/defines.inc.php est refusée" "$(ok "$?" 2)"

# — surcharge projet : ajout d'un module, retrait d'une entrée générique —
L=$("$SCRIPT" --list "$SITE")
check "la surcharge projet ajoute le module"  "$(ok "$(grep -cE 'data/modules/demo[[:space:]]' <<<"$L")" 1)"
check "une cible « - » retire l'entrée"       "$(ok "$(grep -c 'data/cms-img' <<<"$L")" 0)"
check "la surcharge VERSIONNÉE du site est lue" "$(ok "$(grep -cE 'data/modules/demo2[[:space:]]' <<<"$L")" 1)"

# — check AVANT création : non conforme, et rien d'écrit —
"$SCRIPT" --check "$SITE" >/dev/null 2>&1
check "--check sort en erreur quand data/ manque" "$(ok "$?" 1)"
check "--check n'a rien créé" "$(ok "$([ -e "$SITE/data" ] && echo y || echo n)" n)"

# — dry-run : annonce, n'écrit pas —
"$SCRIPT" --ensure --dry-run "$SITE" >/dev/null 2>&1
check "--dry-run n'a rien créé" "$(ok "$([ -e "$SITE/data" ] && echo y || echo n)" n)"

# — création —
OUT=$("$SCRIPT" --ensure "$SITE" 2>&1); RC=$?
check "--ensure réussit" "$(ok "$RC" 0)"
check "data/product-img est un lien" "$(ok "$([ -L "$SITE/data/product-img" ] && echo y || echo n)" y)"
check "le lien est RELATIF" "$(ok "$(readlink "$SITE/data/product-img")" "../img/p")"
check "le lien d'un module remonte de deux niveaux" \
      "$(ok "$(readlink "$SITE/data/modules/demo")" "../../modules/demo/img")"
check "le lien résout vers la vraie donnée" \
      "$(ok "$(cat "$SITE/data/product-img/1/1.jpg")" "photo")"
check "upload est relié" "$(ok "$(cat "$SITE/data/upload/abc.pdf")" "piece")"
check ".htaccess refuse tout" "$(ok "$(grep -c 'Require all denied' "$SITE/data/.htaccess")" 1)"

# — RIEN N'A BOUGÉ —
APRES=$(find "$SITE/img" "$SITE/upload" "$SITE/download" "$SITE/modules" -type f | sort)
check "AUCUNE donnée déplacée ni supprimée" "$(ok "$AVANT" "$APRES")"

# — idempotence —
OUT2=$("$SCRIPT" --ensure "$SITE" 2>&1)
check "rejoué, --ensure ne crée rien" "$(ok "$(grep -c 'créé(s)' <<<"$OUT2")" 1)"
check "rejoué, tout est déjà bon" "$(ok "$(grep -c '0 créé(s), 0 réparé(s)' <<<"$OUT2")" 1)"
"$SCRIPT" --check "$SITE" >/dev/null 2>&1
check "--check est vert après --ensure" "$(ok "$?" 0)"

# — réparation d'un lien faux —
ln -sfn "/ailleurs" "$SITE/data/product-img"
"$SCRIPT" --check "$SITE" >/dev/null 2>&1
check "--check voit un lien qui pointe ailleurs" "$(ok "$?" 1)"
"$SCRIPT" --ensure "$SITE" >/dev/null 2>&1
check "--ensure le répare" "$(ok "$(readlink "$SITE/data/product-img")" "../img/p")"

# — un VRAI dossier à la place : on s'arrête, on ne détruit rien —
rm "$SITE/data/download"; mkdir "$SITE/data/download"; echo "precieux" > "$SITE/data/download/x"
OUT3=$("$SCRIPT" --ensure "$SITE" 2>&1); RC3=$?
check "un vrai dossier dans data/ fait échouer --ensure" "$(ok "$RC3" 1)"
check "le fichier précieux est intact" "$(ok "$(cat "$SITE/data/download/x")" "precieux")"
check "le refus est explicite" "$(ok "$(grep -c "n'est pas un lien" <<<"$OUT3")" 1)"
rm -rf "$SITE/data/download"

# — cible absente : pas de lien pendant —
rm -rf "$SITE/img/pr" "$SITE/data/profile-img"
OUT4=$("$SCRIPT" --ensure "$SITE" 2>&1); RC4=$?
check "une cible absente fait sortir en erreur" "$(ok "$RC4" 1)"
check "aucun lien pendant n'est créé" "$(ok "$([ -e "$SITE/data/profile-img" ] || [ -L "$SITE/data/profile-img" ] && echo y || echo n)" n)"
check "le dossier de données n'est pas créé à la place de PS" \
      "$(ok "$([ -d "$SITE/img/pr" ] && echo y || echo n)" n)"

if [ "$fails" != 0 ]; then echo; echo "ÉCHEC : $fails test(s)"; exit 1; fi
echo; echo "OK — presta-data-index (rien n'est jamais déplacé)"
