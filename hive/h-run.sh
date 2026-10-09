#!/usr/bin/env bash
set -euo pipefail
ROOT="${LACKMINER_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)}"
cd "$ROOT"
source h-manifest.conf
mapfile -t config < "$CUSTOM_CONFIG_FILENAME"
wallet="${config[0]:-}"
./lackminer-qbtc --validate-address --user "$wallet"
read -r -a supplied <<< "${config[1]:-}"
selection=all
selection_set=false
options=()
for ((i=0;i<${#supplied[@]};i++)); do
  arg="${supplied[$i]}"
  case "$arg" in
    --device|--devices)
      [[ "$selection_set" == false && $((i+1)) -lt ${#supplied[@]} ]] || { echo 'Specify --devices once, with a value' >&2; exit 1; }
      i=$((i+1)); selection="${supplied[$i]}"; selection_set=true ;;
    --node-dir)
      [[ $((i+1)) -lt ${#supplied[@]} ]] || { echo 'Missing value for --node-dir' >&2; exit 1; }
      i=$((i+1)); export LACKMINER_NODE_DIR="${supplied[$i]}" ;;
    --debug) options+=("$arg") ;;
    --max-power|--power-limit|--power-percent|--core-clock|--memory-clock|--fan|--intensity|--max-temp|--max-hotspot|--worksize|--batch|--unroll|--min-height)
      [[ $((i+1)) -lt ${#supplied[@]} ]] || { echo "Missing value for $arg" >&2; exit 1; }
      i=$((i+1)); options+=("$arg" "${supplied[$i]}") ;;
    *) echo "Unsupported Hive argument: $arg" >&2; exit 1 ;;
  esac
done
if [[ -z "${LACKMINER_NODE_DIR:-}" ]]; then
  if [[ -x "$ROOT/node/official/v2.5.0/quantum-btc" ]]; then export LACKMINER_NODE_DIR="$ROOT/node"; else export LACKMINER_NODE_DIR=/hive/opt/lackminer-qbtc/node; fi
fi
umask 077
state_dir="$ROOT/_hive"
mkdir -p "$state_dir" "$(dirname "$CUSTOM_LOG_BASENAME")"
exec 8>"$state_dir/worker.lock"
flock -n 8 || { echo 'Another worker supervisor is already running' >&2; exit 1; }
inventory=$(./lackminer-qbtc --list-devices-json)
if [[ "$selection" == all ]]; then
  selected=$(jq -c 'map(select(.vendor|test("NVIDIA|Advanced Micro Devices|AMD";"i"))) | unique_by(.pci // ("opencl:"+(.index|tostring))) | sort_by(.index)' <<< "$inventory")
else
  [[ "$selection" =~ ^[0-9]+(,[0-9]+)*$ ]] || { echo 'Use --devices all or --devices 0,1,2' >&2; exit 1; }
  indices=$(jq -cn --arg value "$selection" '$value|split(",")|map(tonumber)')
  selected=$(jq -ce --argjson ids "$indices" '
    . as $all | [$ids[] as $id | ($all[] | select(.index==$id))] as $chosen |
    if ($ids|length)!=($ids|unique|length) or ($chosen|length)!=($ids|length) or ($chosen|unique_by(.pci // ("opencl:"+(.index|tostring)))|length)!=($chosen|length)
    then error("Invalid, duplicate or unavailable GPU selection") else $chosen end' <<< "$inventory")
fi
count=$(jq 'length' <<< "$selected")
[[ "$count" -gt 0 && "$count" -le 256 ]] || { echo 'No supported GPUs selected' >&2; exit 1; }
jq -c 'map(. + {bus:(if (.pci // "" | test("^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:")) then (.pci|split(":")[1]|ascii_downcase|explode|reduce .[] as $c (0; . * 16 + (if $c>=48 and $c<=57 then $c-48 else $c-87 end))) else null end)})' <<< "$selected" > "$state_dir/gpus.json"
mapfile -t devices < <(jq -r '.[].index' "$state_dir/gpus.json")
printf '%s\n' "$(date +%s)" > "$state_dir/started_at"
seed=$(date +%s%N)
declare -A pids retry_at
guardian=0
node_watcher=0
stopping=false
capture_counts(){
  local id="$1"
  if [[ -f "$state_dir/gpu-$id.json" ]]; then
    jq -sc '.[0] as $old | .[1] as $current | {accepted:(($old.accepted//0)+($current.accepted//0)),rejected:(($old.rejected//0)+($current.rejected//0)),stale:(($old.stale//0)+($current.stale//0))}' "$state_dir/history-$id.json" "$state_dir/gpu-$id.json" > "$state_dir/history-$id.tmp" && mv -- "$state_dir/history-$id.tmp" "$state_dir/history-$id.json"
  fi
  rm -f -- "$state_dir/gpu-$id.json"
}
cleanup(){
  [[ "$stopping" == false ]] || return 0
  stopping=true
  trap '' INT TERM
  for pid in "$guardian" "$node_watcher" "${pids[@]}"; do [[ "$pid" -gt 0 ]] && kill -TERM "$pid" 2>/dev/null || true; done
  local deadline=$((SECONDS+10)) alive
  while (( SECONDS<deadline )); do
    alive=false
    for pid in "$guardian" "$node_watcher" "${pids[@]}"; do if [[ "$pid" -gt 0 ]] && kill -0 "$pid" 2>/dev/null; then alive=true; fi; done
    [[ "$alive" == true ]] || break
    sleep 0.2
  done
  for pid in "$guardian" "$node_watcher" "${pids[@]}"; do [[ "$pid" -gt 0 ]] && kill -KILL "$pid" 2>/dev/null || true; done
  for id in "${devices[@]}"; do if [[ -f "$state_dir/history-$id.json" ]]; then capture_counts "$id"; fi; done
  rm -f -- "$state_dir/chain.json"
}
trap cleanup EXIT
trap 'exit 0' INT TERM
bash ./node-linux.sh 8>&-
next_node_check=$((SECONDS+15))
for id in "${devices[@]}"; do
  pids[$id]=0; retry_at[$id]=0
  printf '{"accepted":0,"rejected":0,"stale":0}\n' > "$state_dir/history-$id.json"
  rm -f -- "$state_dir/gpu-$id.json"
done
echo "SOLO worker: $count GPUs, one local node, payout $wallet" >>"${CUSTOM_LOG_BASENAME}.log"
while true; do
  if (( SECONDS>=next_node_check )); then
    if [[ "$node_watcher" == 0 ]] || ! kill -0 "$node_watcher" 2>/dev/null; then
      if [[ "$node_watcher" != 0 ]]; then wait "$node_watcher" || true; fi
      bash ./node-linux.sh >>"${CUSTOM_LOG_BASENAME}-node.log" 2>&1 8>&- &
      node_watcher=$!
    fi
    next_node_check=$((SECONDS+15))
  fi
  if [[ "$guardian" == 0 ]] || ! kill -0 "$guardian" 2>/dev/null; then
    if [[ "$guardian" != 0 ]]; then wait "$guardian" || true; fi
    rm -f -- "$state_dir/chain.json"
    ./lackminer-qbtc --chain-watch --node http://127.0.0.1:24002 --user "$wallet" --chain-state "$state_dir/chain.json" >>"${CUSTOM_LOG_BASENAME}-chain.log" 2>&1 8>&- &
    guardian=$!
  fi
  for ((lane=0;lane<count;lane++)); do
    id="${devices[$lane]}"
    if [[ "${pids[$id]}" != 0 ]] && ! kill -0 "${pids[$id]}" 2>/dev/null; then
      wait "${pids[$id]}" || true
      capture_counts "$id"
      pids[$id]=0; retry_at[$id]=$((SECONDS+10))
      echo "GPU$id stopped; restarting in 10 seconds" >>"${CUSTOM_LOG_BASENAME}.log"
    fi
    if [[ "${pids[$id]}" == 0 && "$SECONDS" -ge "${retry_at[$id]}" ]]; then
      ./lackminer-qbtc --solo --node http://127.0.0.1:24002 --user "$wallet" --device "$id" --nonce-base "$seed" --nonce-lane "$lane" --nonce-lanes "$count" --chain-state "$state_dir/chain.json" --stats-file "$state_dir/gpu-$id.json" --log-file "${CUSTOM_LOG_BASENAME}-gpu$id.jsonl" "${options[@]}" >>"${CUSTOM_LOG_BASENAME}-gpu$id.log" 2>&1 8>&- &
      pids[$id]=$!
    fi
  done
  sleep 1
done
