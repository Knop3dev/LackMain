#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
source h-manifest.conf
export LACKMINER_DATA="$PWD/data"
mode=$(jq -r '.mode' "$CUSTOM_CONFIG_FILENAME")
args=()
[[ "$mode" != pool ]] || args+=(--start)
mkdir -p "$(dirname "$CUSTOM_LOG_BASENAME")"
exec ./lackminer-lbtc --config "$CUSTOM_CONFIG_FILENAME" --panel --no-browser --port 8808 "${args[@]}" 2>&1 | tee -a "$CUSTOM_LOG_BASENAME.log"
