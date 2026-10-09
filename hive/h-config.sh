#!/usr/bin/env bash
[[ -n "${CUSTOM_CONFIG_FILENAME:-}" ]] || { echo 'Missing Hive miner manifest' >&2; return 1; }
wallet="${CUSTOM_TEMPLATE:-}"
[[ "$wallet" =~ ^qbtc1[0-9a-z]+$ ]] || { echo 'Set a Q-BTC payout address as Wallet template' >&2; return 1; }
printf '%s\n' "$wallet" "${CUSTOM_USER_CONFIG:-}" > "$CUSTOM_CONFIG_FILENAME"
