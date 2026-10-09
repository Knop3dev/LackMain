#!/usr/bin/env bash
khs=0
stats='null'
root="${LACKMINER_ROOT:-/hive/miners/custom/lackminer-qbtc}"
state_dir="$root/_hive"
if [[ -f "$state_dir/gpus.json" ]]; then
  now=$(date +%s)
  started=$(cat "$state_dir/started_at" 2>/dev/null || printf '%s' "$now")
  rows=()
  while read -r id; do
    current='{}'; history='{}'
    if [[ -f "$state_dir/gpu-$id.json" ]]; then current=$(jq -c . "$state_dir/gpu-$id.json" 2>/dev/null || printf '{}'); fi
    if [[ -f "$state_dir/history-$id.json" ]]; then history=$(jq -c . "$state_dir/history-$id.json" 2>/dev/null || printf '{}'); fi
    now=$(date +%s)
    row=$(jq -cn --argjson now "$now" --argjson id "$id" --argjson s "$current" --argjson h "$history" '
      ($s.event=="stats" and (($s.updated_at//0)<=$now) and (($now-($s.updated_at//0))<=15)) as $live |
      {index:$id,hashrate:(if $live then ($s.hashrate//0) else 0 end),temperature:(if $live then $s.controls.gpu.temperature else null end),fan:(if $live then $s.controls.gpu.fan_percent else null end),power:(if $live then $s.controls.gpu.power else null end),accepted:(($h.accepted//0)+($s.accepted//0)),rejected:(($h.rejected//0)+($s.rejected//0)),stale:(($h.stale//0)+($s.stale//0))}')
    rows+=("$row")
  done < <(jq -r '.[].index' "$state_dir/gpus.json")
  if [[ ${#rows[@]} -gt 0 ]]; then
    now=$(date +%s)
    stats=$(printf '%s\n' "${rows[@]}" | jq -sc --slurpfile gpu "$state_dir/gpus.json" --argjson uptime "$((now-started))" '
      {hs:map(.hashrate),hs_units:"hs",temp:map(.temperature),fan:map(.fan),power:map(.power),uptime:$uptime,ver:"0.2.1",ar:[(map(.accepted)|add),(map(.rejected)|add)],stale:(map(.stale)|add),algo:"qbtc",bus_numbers:($gpu[0]|map(.bus))}')
    khs=$(jq -r '(.hs|add)/1000' <<< "$stats")
  fi
fi
