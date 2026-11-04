#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$root/h-manifest.conf"
mode="${CUSTOM_USER_CONFIG:-pool}"
[[ "$mode" == solo || "$mode" == pool ]] || { echo 'Extra config: solo or pool' >&2; exit 1; }
[[ -n "${CUSTOM_TEMPLATE:-}" ]] || { echo 'Set your LBTC address as Wallet template' >&2; exit 1; }
devices=$("$root/lackminer-lbtc" --list-devices | jq -c '[.devices[].id]')
umask 077
jq -n --arg address "$CUSTOM_TEMPLATE" --arg mode "$mode" --argjson devices "$devices" '{address:$address,mode:$mode,node:"https://latebitcoiners.com",devices:$devices,cpu_workers:0,worksize:128,batch:1048576,intensity:80,max_temperature:80,max_hotspot:85,auto_restart:true,tuning:{}}' > "$CUSTOM_CONFIG_FILENAME"
