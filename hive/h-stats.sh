#!/usr/bin/env bash
khs=0
stats='null'
datafile="${LACKMINER_STATS_FILE:-/hive/miners/custom/lackminer-qbtc/stats.json}"
if [[ -f "$datafile" ]]; then
  now=$(date +%s)
  if jq -e --argjson now "$now" '(.event == "stats") and (.updated_at <= $now) and (($now - .updated_at) <= 15)' "$datafile" >/dev/null 2>&1; then
    khs=$(jq -r '(.hashrate // 0) / 1000' "$datafile")
    pci=$(jq -r '.gpu_pci // empty' "$datafile")
    bus=null
    if [[ "$pci" =~ ^[0-9a-fA-F]{4}:([0-9a-fA-F]{2}):[0-9a-fA-F]{2}\.[0-7]$ ]]; then bus=$((16#${BASH_REMATCH[1]})); fi
    stats=$(jq -c --argjson bus "$bus" '{hs:[.hashrate // 0],hs_units:"hs",temp:[.controls.gpu.temperature],fan:[.controls.gpu.fan_percent],uptime:(.elapsed_seconds|floor),ver:"0.2.0",ar:[.accepted // 0,.rejected // 0],algo:"qbtc",bus_numbers:[$bus]}' "$datafile")
  fi
fi
