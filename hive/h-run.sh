#!/usr/bin/env bash
set -euo pipefail
cd /hive/miners/custom/lackminer-qbtc
source h-manifest.conf
mapfile -t config < "$CUSTOM_CONFIG_FILENAME"
wallet="${config[0]:-}"
./lackminer-qbtc --validate-address --user "$wallet"
read -r -a options <<< "${config[1]:-}"
for arg in "${options[@]}"; do
  case "$arg" in --user|--node|--pool|--stats-file|--log-file|--benchmark|--gpu-benchmark|--tune|--self-test|--list-devices) echo "Reserved Hive argument: $arg" >&2; exit 1 ;; esac
done
bash ./node-linux.sh
mkdir -p "$(dirname "$CUSTOM_LOG_BASENAME")"
exec ./lackminer-qbtc --solo --node http://127.0.0.1:24002 --user "$wallet" --stats-file ./stats.json --log-file "${CUSTOM_LOG_BASENAME}.jsonl" "${options[@]}" >>"${CUSTOM_LOG_BASENAME}.log" 2>&1
