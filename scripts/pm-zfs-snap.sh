#!/usr/bin/env bash
# pm-zfs-snap.sh — wrapper PM pour créer / lister / supprimer des snapshots ZFS,
# destiné à être délégué via sudoers (NOPASSWD). TOUTE la validation est ici, de
# sorte que la délégation sudo reste cantonnée : on ne peut agir que sur des
# datasets du périmètre autorisé et sur des *snapshots* nommés (jamais détruire
# un dataset/filesystem). Utilisé notamment comme filet de sûreté par les
# migrations de workspace (pm-env-migrate : snapshot manuel + --no-snapshot).
#
# Sécurité : tant que ce fichier n'est pas root-owned, quiconque peut l'éditer
# obtient root via le sudoers. La cible est de passer les scripts PM root-owned ;
# d'ici là, la délégation est consentie en connaissance de cause.
#
# Usage :
#   sudo pm-zfs-snap.sh create  <dataset> <snapname>
#   sudo pm-zfs-snap.sh destroy <dataset> <snapname>
#   sudo pm-zfs-snap.sh list    [<dataset>]
set -euo pipefail

ZFS=/usr/sbin/zfs
ALLOWED_PREFIX="zfs/workspaces"   # dataset autorisé (lui-même + descendants)
NAME_RE='^[A-Za-z0-9._:-]+$'      # charset sûr pour un nom de snapshot

die()   { echo "pm-zfs-snap: $*" >&2; exit 1; }
usage() { echo "usage: pm-zfs-snap.sh {create|destroy|list} <dataset> [snapname]" >&2; exit 2; }

check_dataset() {
  local ds="$1"
  [[ "$ds" == "$ALLOWED_PREFIX" || "$ds" == "$ALLOWED_PREFIX"/* ]] \
    || die "dataset '$ds' hors périmètre autorisé ($ALLOWED_PREFIX)"
}

check_snapname() {
  local s="$1"
  [[ -n "$s" && "$s" =~ $NAME_RE ]] || die "nom de snapshot invalide : '$s'"
  [[ "$s" != *@* ]] || die "le nom de snapshot ne doit pas contenir '@'"
}

cmd="${1:-}"; ds="${2:-}"; snap="${3:-}"
[[ -n "$cmd" ]] || usage

case "$cmd" in
  create)
    [[ -n "$ds" && -n "$snap" ]] || usage
    check_dataset "$ds"; check_snapname "$snap"
    exec "$ZFS" snapshot "${ds}@${snap}"
    ;;
  destroy)
    [[ -n "$ds" && -n "$snap" ]] || usage
    check_dataset "$ds"; check_snapname "$snap"
    # garde-fou : cible toujours un snapshot nommé, jamais le dataset nu
    exec "$ZFS" destroy "${ds}@${snap}"
    ;;
  list)
    ds="${ds:-$ALLOWED_PREFIX}"
    check_dataset "$ds"
    exec "$ZFS" list -t snapshot -o name,used,creation -s creation -r "$ds"
    ;;
  *)
    usage
    ;;
esac
