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
read -r -p "Public Q-BTC payout address [$wallet]: " answer
wallet="${answer:-$wallet}"
"$MINER" --validate-address --user "$wallet"
"$MINER" --list-devices
read -r -p "GPU index [$device]: " answer
device="${answer:-$device}"
read -r -p "Measured power budget in W [$power]: " answer
power="${answer:-$power}"
read -r -p "Intensity 1..100 [$intensity]: " answer
intensity="${answer:-$intensity}"
echo 'Fee: 10% of the entire coinbase (subsidy + transaction fees); 90% to your address.'
read -r -p 'Start SOLO mining? Type YES: ' confirm
[[ "$confirm" == YES ]] || exit 0
printf '%s\n' "$wallet" "$device" "$power" "$intensity" > "$CONFIG"
bash "$ROOT/node-linux.sh"
while true; do
  "$MINER" --solo --node http://127.0.0.1:24002 --user "$wallet" --device "$device" --max-power "$power" --intensity "$intensity" --log-file "$ROOT/miner.jsonl" --stats-file "$ROOT/stats.json" && break
  echo 'Miner failed; retrying in 10 seconds. Ctrl+C to stop.'
  sleep 10
done
