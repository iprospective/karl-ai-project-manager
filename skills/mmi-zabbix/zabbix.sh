#!/usr/bin/env bash
# mmi-zabbix — façade orchestrateur PM : pilote Zabbix VIA atlas (RM2398).
#
# AUCUN secret Zabbix ni appel JSON-RPC côté PM (D3, RM2421). Délègue au canal
# orchestrateur atlas (SSH forced-command, RM2516) → catalogue atlas (RM2496) →
# client Zabbix (RM2454). Le token Zabbix reste chez atlas (ATLAS_ZABBIX_*).
#
#   zabbix.sh ops                         # liste les ops zbx-* du catalogue
#   zabbix.sh host <fqdn>                 # état structuré d'un hôte
#   zabbix.sh items <fqdn>                # items + dernières valeurs
#   zabbix.sh problems [fqdn]             # problèmes actifs (hôte optionnel)
#   zabbix.sh lld <fqdn>                  # règles de découverte (LLD)
#   zabbix.sh ack <eventid> <message> [--dry-run]   # acquitter (action=6, pas de close)
#   zabbix.sh lld-run <ruleid> [--dry-run]          # LLD « execute now »
#
# Sortie : JSON du cœur atlas ({ok, stdout:<JSON zbx>, ...}). Les verbes P2 (disable /
# link-template) sont refusés par le cœur (droit atlas-orch zbx-only P1) — volontaire.
#
# Config : ATLAS_ORCH_KEY (défaut ~/.ssh/id_ed25519_karl),
#          ATLAS_ORCH_HOST (défaut atlas-orch@atlas.iprospective.net).
set -euo pipefail
: "${ATLAS_ORCH_KEY:=$HOME/.ssh/id_ed25519_karl}"
: "${ATLAS_ORCH_HOST:=atlas-orch@atlas.iprospective.net}"

[ "$#" -ge 1 ] || { echo "usage: zabbix.sh <ops|host|items|problems|lld|ack|lld-run> …" >&2; exit 2; }
verb="$1"; shift

# --dry-run peut être placé n'importe où (verbes d'action).
dry=(); rest=()
for a in "$@"; do
  if [ "$a" = "--dry-run" ]; then dry+=("--dry-run"); else rest+=("$a"); fi
done

case "$verb" in
  ops)                     argv=(ops) ;;
  host|items|problems|lld) argv=(run "zbx-$verb" ${rest[@]+"${rest[@]}"}) ;;
  ack)                     argv=(run ${dry[@]+"${dry[@]}"} zbx-ack ${rest[@]+"${rest[@]}"}) ;;
  lld-run)                 argv=(run ${dry[@]+"${dry[@]}"} zbx-lld-run ${rest[@]+"${rest[@]}"}) ;;
  *) echo "verbe inconnu : $verb (ops|host|items|problems|lld|ack|lld-run)" >&2; exit 2 ;;
esac

# Encodage base64(JSON) — robuste aux espaces/guillemets, aucun word-splitting distant.
payload=$(python3 -c \
  'import base64,json,sys; print(base64.b64encode(json.dumps(sys.argv[1:]).encode()).decode())' \
  "${argv[@]}")

exec ssh -i "$ATLAS_ORCH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
     "$ATLAS_ORCH_HOST" "atlas $payload"
