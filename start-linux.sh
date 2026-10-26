#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
MINER="$ROOT/lackminer-qbtc"
CONFIG="$ROOT/miner-config.txt"
if [[ -f "$CONFIG" ]]; then mapfile -t C < "$CONFIG"; else C=(); fi
wallet="${C[0]:-}"
device="${C[1]:-0}"
power="${C[2]:-120}"
intensity="${C[3]:-100}"
mode="${C[4]:-pool}"
backend="${C[5]:-gpu}"
threads="${C[6]:-2}"
pool="${C[7]:-stratum+tcp://ashenward.ru:3334}"
read -r -p "Mode: pool or solo [$mode]: " answer
mode="${answer:-$mode}"
[[ "$mode" == pool || "$mode" == solo ]] || { echo 'Choose pool or solo';exit 1; }
if [[ "$mode" == pool ]]; then
  read -r -p "Backend: cpu or gpu [$backend]: " answer
  backend="${answer:-$backend}"
  [[ "$backend" == cpu || "$backend" == gpu ]] || { echo 'Choose cpu or gpu';exit 1; }
fi
read -r -p "Public Q-BTC payout address [$wallet]: " answer
wallet="${answer:-$wallet}"
"$MINER" --validate-address --user "$wallet"
if [[ "$mode" == pool && "$backend" == cpu ]]; then
  read -r -p "CPU threads [$threads]: " answer
  threads="${answer:-$threads}"
else
"$MINER" --list-devices
read -r -p "GPU index [$device]: " answer
device="${answer:-$device}"
read -r -p "Measured power budget in W [$power]: " answer
power="${answer:-$power}"
read -r -p "Intensity 1..100 [$intensity]: " answer
intensity="${answer:-$intensity}"
fi
if [[ "$mode" == pool ]]; then
  read -r -p "Pool URL [$pool]: " answer
  pool="${answer:-$pool}"
  echo 'LackPool: 1.5% fee, proportional rewards, minimum payout 10 QBTC. No additional SOLO fee.'
else
  echo 'SOLO: 10% of the entire coinbase (subsidy and transaction fees).'
fi
read -r -p 'Start mining? Type YES: ' confirm
[[ "$confirm" == YES ]] || exit 0
printf '%s\n' "$wallet" "$device" "$power" "$intensity" "$mode" "$backend" "$threads" "$pool" > "$CONFIG"
if [[ "$mode" == pool ]]; then
  worker="$(hostname -s)";worker="${worker//[^a-zA-Z0-9_-]/_}"
  args=(--pool "$pool" --user "$wallet.$worker" --log-file "$ROOT/miner.jsonl" --stats-file "$ROOT/stats.json")
  if [[ "$backend" == cpu ]]; then args+=(--cpu --cpu-threads "$threads");else args+=(--device "$device" --max-power "$power" --intensity "$intensity");fi
  exec "$MINER" "${args[@]}"
fi
bash "$ROOT/node-linux.sh"
while true; do
  "$MINER" --solo --node http://127.0.0.1:24002 --user "$wallet" --device "$device" --max-power "$power" --intensity "$intensity" --log-file "$ROOT/miner.jsonl" --stats-file "$ROOT/stats.json" && break
  echo 'Miner failed; retrying in 10 seconds. Ctrl+C to stop.'
  sleep 10
done
