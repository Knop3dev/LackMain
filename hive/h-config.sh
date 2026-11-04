#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$root/h-manifest.conf"
extra="${CUSTOM_USER_CONFIG:-pool}"
if [[ "$extra" == solo || "$extra" == pool ]]; then
  options=$(jq -cn --arg mode "$extra" '{mode:$mode}')
else
  options=$(jq -ce 'if type=="object" and (keys-["mode","devices","cpu_workers","worksize","batch","intensity","max_temperature","max_hotspot","auto_restart"]|length)==0 then . else error("Unsupported extra config") end' <<< "$extra")
fi
[[ -n "${CUSTOM_TEMPLATE:-}" ]] || { echo 'Set your LBTC address as Wallet template' >&2; exit 1; }
devices=$("$root/lackminer-lbtc" --list-devices | jq -c '[.devices[].id]')
umask 077
jq -n --arg address "$CUSTOM_TEMPLATE" --argjson options "$options" --argjson devices "$devices" '{address:$address,mode:"pool",node:"https://latebitcoiners.com",devices:$devices,cpu_workers:0,worksize:128,batch:1048576,intensity:80,max_temperature:80,max_hotspot:85,auto_restart:true,tuning:{}} * $options' > "$CUSTOM_CONFIG_FILENAME"
