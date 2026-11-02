#!/bin/bash
# Tests RM3619 — presta-nonprod-sql.sh : les modules de SUIVI PUBLICITAIRE et d'audience
# sont désactivés sur toute copie non-prod d'un PrestaShop.
#
# Ce que ces tests protègent :
#
#   * PAR DÉFAUT, le SQL émis désactive les modules de suivi (pixel Meta, Google Ads,
#     Analytics, Tag Manager) : c'est le cas que les appelants (synchro, pm-env-session)
#     utilisent sans option. Incident fondateur RM3616 : une recette calicote indexée
#     déclenchait les pixels de la prod à chaque visite ;
#   * les modules CLOUD (RM2932) restent désactivés : les deux listes s'additionnent ;
#   * --tracking-modules remplace la liste, --keep-tracking la retire, sans toucher
#     aux modules cloud ;
#   * un nom de module invalide est refusé (le nom finit dans du SQL) ;
#   * --no-disable-modules continue de ne désactiver AUCUN module.
#
# Lancer : bash scripts/test_presta_nonprod_sql.sh
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT="$HERE/../tools/env-runtime/presta-nonprod-sql.sh"
fails=0

check() { if [ "$2" = 0 ]; then echo "✓ $1"; else echo "✗ $1"; fails=$((fails + 1)); fi; }
has() { grep -qF -- "$2" <<<"$1" && echo 0 || echo 1; }
hasnt() { grep -qF -- "$2" <<<"$1" && echo 1 || echo 0; }

# La ligne UPDATE des modules de suivi, isolée pour ne pas confondre avec la liste cloud.
tracking_line() { grep -A1 -- '-- 4\.' <<<"$1" | grep 'UPDATE' || true; }

out=$("$SCRIPT" --domain x.test.iprospective.fr); rc=$?
check "défaut : exit 0" "$rc"
t=$(tracking_line "$out")
for m in facebookproductad gadwordstracking ps_googleanalytics cdc_googletagmanager ps_facebook psxmarketingwithgoogle; do
  check "défaut : $m désactivé" "$(has "$t" "'$m'")"
done
check "défaut : UPDATE active = 0 sur ps_module" "$(has "$t" 'UPDATE `ps_module` SET active = 0 WHERE name IN (')"
check "défaut : modules cloud toujours désactivés" "$(has "$out" "'ps_accounts'")"

out=$("$SCRIPT" --prefix abc_ --domain x.local)
check "préfixe appliqué aux modules de suivi" "$(has "$(tracking_line "$out")" 'UPDATE `abc_module`')"

out=$("$SCRIPT" --domain x.local --tracking-modules "monpixel autre_tag")
t=$(tracking_line "$out")
check "--tracking-modules : liste remplacée" "$(has "$t" "'monpixel', 'autre_tag'")"
check "--tracking-modules : l'ancienne liste disparaît" "$(hasnt "$t" "'facebookproductad'")"

out=$("$SCRIPT" --domain x.local --keep-tracking)
check "--keep-tracking : aucun UPDATE de suivi" "$(ok_empty=$(tracking_line "$out"); [ -z "$ok_empty" ] && echo 0 || echo 1)"
check "--keep-tracking : le dit en commentaire" "$(has "$out" '-- 4. Modules de suivi : laissés en l')"
check "--keep-tracking : modules cloud toujours désactivés" "$(has "$out" "'ps_accounts'")"

out=$("$SCRIPT" --domain x.local --no-disable-modules)
check "--no-disable-modules : aucun UPDATE de module" "$(hasnt "$out" 'SET active = 0')"

"$SCRIPT" --domain x.local --tracking-modules "ok bad;drop" >/dev/null 2>&1; rc=$?
check "nom de module de suivi invalide refusé (exit 2)" "$([ "$rc" = 2 ] && echo 0 || echo 1)"

echo
if [ "$fails" = 0 ]; then echo "OK — tous les tests passent"; else echo "ÉCHEC — $fails test(s)"; exit 1; fi
