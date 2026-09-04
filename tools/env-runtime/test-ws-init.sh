#!/bin/bash
# Tests des gardes de `ws-init` / `ws-perms` (RM2909) — SANS privilège.
#
# Le helper meurt en tête s'il n'est pas root : on EXTRAIT donc le bloc de fonctions
# `ws_*` du fichier de PRODUCTION (entre son marqueur d'ouverture et le dispatch) et on
# le source avec `die` stubbé. Aucune règle n'est recopiée ici — un garde-fou retiré du
# helper fait tomber le test correspondant.
#
# Lancer : bash tools/env-runtime/test-ws-init.sh
set -uo pipefail

HELPER="$(cd "$(dirname "$0")" && pwd)/pm-env-helper.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
LIB="$TMP/lib.sh"

{
    echo 'die() { echo "pm-env-helper: $*" >&2; exit 1; }'
    echo 'audit() { :; }'
    echo 'WS_ROOT="/zfs/workspaces"'
    awk '/^# -+ squelette workspace \(RM2909\)/ {f=1} /^case "\$verb" in/ {f=0} f' "$HELPER"
} > "$LIB"

grep -q 'ws_resolve()' "$LIB" || { echo "✗ extraction du bloc ws_* ratée"; exit 1; }

# Le helper vise le core DÉPLOYÉ (/zfs/workspaces/.mmi-pm-core) : les deux partent par le
# même canal `mmi-pm core update`, mais dans un worktree de dev le core est en retard. Le
# contrat de modèle se teste donc contre le pm-perms DE LA BRANCHE, avec le contrôle
# root-owned neutralisé — ce contrôle a son propre test, plus bas.
REPO=$(cd "$(dirname "$0")/../.." && pwd)
LIB_REPO="$TMP/lib-repo.sh"
{
    cat "$LIB"
    printf 'PM_PERMS=%q\n' "$REPO/scripts/pm-perms.py"
    echo 'pm_perms_check() { :; }'
} > "$LIB_REPO"

ok=0; ko=0
call()      { bash -c 'set -uo pipefail; . "$1"; shift; "$@"' _ "$LIB" "$@" 2>&1; }
call_repo() { bash -c 'set -uo pipefail; . "$1"; shift; "$@"' _ "$LIB_REPO" "$@" 2>&1; }

reject() {  # $1 = argument, $2 = fragment attendu du message de refus
    local out
    if out=$(call ws_resolve "$1"); then
        echo "✗ « $1 » ACCEPTÉ (→ $out), attendu refusé"; ko=$((ko + 1)); return
    fi
    if [[ "$out" == *"$2"* ]]; then
        echo "✓ refusé ($2) : ${1:-<vide>}"; ok=$((ok + 1))
    else
        echo "✗ « $1 » refusé mais pour la mauvaise raison : $out"; ko=$((ko + 1))
    fi
}

accept() {  # $1 = argument, $2 = chemin canonique attendu
    local out
    if ! out=$(call ws_resolve "$1"); then
        echo "✗ « $1 » REFUSÉ ($out), attendu accepté"; ko=$((ko + 1)); return
    fi
    if [ "$out" = "$2" ]; then
        echo "✓ accepté : $1 → $out"; ok=$((ok + 1))
    else
        echo "✗ « $1 » → $out, attendu $2"; ko=$((ko + 1))
    fi
}

echo "=== ws_resolve : ce qui passe ==="
accept /zfs/workspaces/iprospective/communication /zfs/workspaces/iprospective/communication
accept /zfs/workspaces/iprospective/communication/ /zfs/workspaces/iprospective/communication
accept /zfs/workspaces/iprospective/./communication /zfs/workspaces/iprospective/communication
accept /zfs/workspaces/client-2/projet.v2 /zfs/workspaces/client-2/projet.v2

echo
echo "=== ws_resolve : ce qui est refusé ==="
reject ""                                    "workspace vide"
reject "iprospective/communication"          "non absolu"
reject "/etc/passwd"                         "hors de"
reject "/zfs/workspaces"                     "hors de"
reject "/zfs/workspaces/iprospective"        "profondeur invalide"
reject "/zfs/workspaces/a/b/c"               "profondeur invalide"
# évasion par ..: realpath normalise AVANT le test de préfixe
reject "/zfs/workspaces/a/../../etc/shadow"  "hors de"
reject "/zfs/workspaces/a/b/../../../etc"    "hors de"
reject "/zfs/workspaces/Iprospective/comm"   "client non conforme"
reject "/zfs/workspaces/iprospective/Comm"   "projet non conforme"
reject "/zfs/workspaces/.hidden/projet"      "client non conforme"
reject "/zfs/workspaces/cli ent/projet"      "client non conforme"

echo
echo "=== ws_model_dirs : contrat avec pm-perms (source unique du modèle) ==="
if out=$(call_repo ws_model_dirs); then
    n=$(printf '%s\n' "$out" | grep -c .)
    if [ "$n" -ge 8 ]; then
        echo "✓ $n dossiers de modèle obtenus de pm-perms --list-dirs"; ok=$((ok + 1))
    else
        echo "✗ seulement $n dossiers — contrat rompu ?"; ko=$((ko + 1))
    fi
    for want in .mmi-pm repos envs tmp sessions logs data .mmi-pm/tasks; do
        if printf '%s\n' "$out" | grep -qx -- "$want"; then
            ok=$((ok + 1))
        else
            echo "✗ $want absent du modèle"; ko=$((ko + 1))
        fi
    done
    echo "✓ dossiers attendus présents (dont les partagés du layout RM1993)"
    if printf '%s\n' "$out" | grep -qx '\.'; then
        echo "✗ « . » (la racine) devrait être filtré — mkdir n'a rien à en faire"; ko=$((ko + 1))
    else
        echo "✓ « . » filtré"; ok=$((ok + 1))
    fi
    # PARENTS D'ABORD : .mmi-pm doit précéder .mmi-pm/tasks
    if [ "$(printf '%s\n' "$out" | grep -nx '\.mmi-pm' | cut -d: -f1)" \
         -lt "$(printf '%s\n' "$out" | grep -nx '\.mmi-pm/tasks' | cut -d: -f1)" ]; then
        echo "✓ ordre parents-avant-enfants respecté"; ok=$((ok + 1))
    else
        echo "✗ .mmi-pm/tasks listé avant son parent"; ko=$((ko + 1))
    fi
else
    echo "✗ ws_model_dirs a échoué : $out"; ko=$((ko + 1))
fi

echo
echo "=== pm_perms_check : refuse d'exécuter en root un script non root-owned ==="
# C'est LA barrière qui empêche un membre du groupe `pm` d'obtenir root en éditant
# pm-perms.py. On la vise avec la copie du worktree (owner = le dev, pas root).
if out=$(bash -c 'set -uo pipefail; . "$1"; PM_PERMS="$2"; PM_CORE=$(dirname "$(dirname "$2")"); pm_perms_check' \
              _ "$LIB" "$REPO/scripts/pm-perms.py" 2>&1); then
    echo "✗ pm_perms_check a ACCEPTÉ un script non root-owned — escalade possible"; ko=$((ko + 1))
else
    [[ "$out" == *"n'appartient pas à root"* || "$out" == *"modifiable hors root"* ]] \
        && { echo "✓ script non root-owned refusé"; ok=$((ok + 1)); } \
        || { echo "✗ refusé, message inattendu : $out"; ko=$((ko + 1)); }
fi
if out=$(bash -c 'set -uo pipefail; . "$1"; pm_perms_check' _ "$LIB" 2>&1); then
    echo "✓ core PROD (root-owned, non modifiable hors root) accepté"; ok=$((ok + 1))
else
    echo "⚠ core PROD refusé sur cette box : $out"
fi

echo
echo "=== ws_no_symlink ==="
mkdir -p "$TMP/reel"; ln -s "$TMP/reel" "$TMP/lien"
if call ws_no_symlink "$TMP/reel" >/dev/null; then
    echo "✓ dossier réel accepté"; ok=$((ok + 1))
else
    echo "✗ dossier réel refusé"; ko=$((ko + 1))
fi
if out=$(call ws_no_symlink "$TMP/lien"); then
    echo "✗ lien symbolique ACCEPTÉ — chmod/chown muteraient sa cible"; ko=$((ko + 1))
else
    [[ "$out" == *"lien symbolique"* ]] \
        && { echo "✓ lien symbolique refusé"; ok=$((ok + 1)); } \
        || { echo "✗ refusé, message inattendu : $out"; ko=$((ko + 1)); }
fi

echo
echo "── $ok test(s) OK, $ko échec(s)"
[ "$ko" -eq 0 ]
