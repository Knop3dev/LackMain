#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
MINER="$ROOT/lackminer-qbtc"
CONFIG="$ROOT/miner-config.txt"
if [[ -f "$CONFIG" ]]; then mapfile -t C < "$CONFIG"; else C=(); fi
wallet="${C[0]:-}"
device="${C[1]:-0}"
power="${C[2]:-0}"
intensity="${C[3]:-100}"
mode="${C[4]:-pool}"
backend="${C[5]:-gpu}"
threads="${C[6]:-2}"
cpu_intensity="${C[8]:-100}"
pool="${C[7]:-stratum+ssl://ashenward.ru:3336}"
if [[ "$pool" == 'stratum+tcp://ashenward.ru:3334' ]]; then pool='stratum+ssl://ashenward.ru:3336'; fi
read -r -p "Mode: pool or solo [$mode]: " answer
mode="${answer:-$mode}"
[[ "$mode" == pool || "$mode" == solo ]] || { echo 'Choose pool or solo';exit 1; }
if [[ "$mode" == pool ]]; then
  read -r -p "Backend: gpu, cpu or cpu-gpu [$backend]: " answer
  backend="${answer:-$backend}"
  [[ "$backend" == cpu || "$backend" == gpu || "$backend" == cpu-gpu ]] || { echo 'Choose gpu, cpu or cpu-gpu';exit 1; }
fi
read -r -p "Public Q-BTC payout address [$wallet]: " answer
wallet="${answer:-$wallet}"
"$MINER" --validate-address --user "$wallet"
if [[ "$mode" == pool && "$backend" != gpu ]]; then
  read -r -p "CPU threads [$threads]: " answer
  threads="${answer:-$threads}"
  read -r -p "CPU intensity 1..100 [$cpu_intensity]: " answer
  cpu_intensity="${answer:-$cpu_intensity}"
fi
if [[ "$mode" == solo || "$backend" != cpu ]]; then
"$MINER" --list-devices
read -r -p "GPU index [$device]: " answer
device="${answer:-$device}"
read -r -p "Measured power budget in W (0 = driver-managed, no power sensor needed) [$power]: " answer
power="${answer:-$power}"
[[ "$power" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo 'Power budget must be 0 or a positive number';exit 1; }
read -r -p "Intensity 1..100 [$intensity]: " answer
intensity="${answer:-$intensity}"
fi
power_args=()
if [[ "$power" =~ [1-9] ]]; then power_args=(--max-power "$power");fi
if [[ "$mode" == pool ]]; then
  read -r -p "Pool URL [$pool]: " answer
  pool="${answer:-$pool}"
  echo 'LackPool: 1.5% fee, PPLNS rewards, minimum payout 10 QBTC. No additional SOLO fee.'
else
  echo 'SOLO: 10% of the entire coinbase (subsidy and transaction fees).'
fi
read -r -p 'Start mining? Type YES: ' confirm
[[ "$confirm" == YES ]] || exit 0
printf '%s\n' "$wallet" "$device" "$power" "$intensity" "$mode" "$backend" "$threads" "$pool" "$cpu_intensity" > "$CONFIG"
if [[ "$mode" == pool ]]; then
  worker="$(hostname -s)";worker="${worker//[^a-zA-Z0-9_-]/_}"
  args=(--pool "$pool" --user "$wallet.$worker" --log-file "$ROOT/miner.jsonl" --stats-file "$ROOT/stats.json")
  if [[ "$backend" != gpu ]]; then args+=("--$backend" --cpu-threads "$threads" --cpu-intensity "$cpu_intensity");fi
  if [[ "$backend" != cpu ]]; then args+=(--device "$device" "${power_args[@]}" --intensity "$intensity");fi
  exec "$MINER" "${args[@]}"
fi
bash "$ROOT/node-linux.sh"
while true; do
  "$MINER" --solo --node http://127.0.0.1:24002 --user "$wallet" --device "$device" "${power_args[@]}" --intensity "$intensity" --log-file "$ROOT/miner.jsonl" --stats-file "$ROOT/stats.json" && break
  echo 'Miner failed; retrying in 10 seconds. Ctrl+C to stop.'
  sleep 10
done
