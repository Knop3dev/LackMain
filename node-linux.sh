#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
NODE_ROOT="${LACKMINER_NODE_DIR:-$ROOT/node}"
NODE_EXE="$NODE_ROOT/official/v2.5.0/quantum-btc"
NODE_URL='http://127.0.0.1:24002'
mkdir -p "$NODE_ROOT/official/v2.5.0" "$NODE_ROOT/data"
if curl --fail --silent --max-time 2 "$NODE_URL/api/get_info" >/dev/null 2>&1; then exit 0; fi
exec 9>"$NODE_ROOT/install.lock"
flock 9
if ! [[ -x "$NODE_EXE" ]]; then
  archive="$NODE_ROOT/qbtc-core-linux.tar.gz"
  curl --fail --location --show-error 'https://github.com/Q-Jack-core/quantum-btc/releases/download/v2.5.0/qbtc-core-linux.tar.gz' --output "$archive"
  printf '%s  %s\n' 'b358f46fbc18617aa469e89c52a15a6aa84238993e40c34cae1cc407f6c786e6' "$archive" | sha256sum --check
  mapfile -t members < <(tar -tzf "$archive" | awk -F/ '$NF == "quantum-btc" {print}')
  [[ ${#members[@]} == 1 ]] || { echo 'Invalid official node archive' >&2; exit 1; }
  tar -xOzf "$archive" "${members[0]}" > "$NODE_EXE.tmp"
  chmod 755 "$NODE_EXE.tmp"
  mv -- "$NODE_EXE.tmp" "$NODE_EXE"
  rm -f -- "$archive"
fi
if ! curl --fail --silent --max-time 2 "$NODE_URL/api/get_info" >/dev/null 2>&1; then
  owned=false
  if [[ -f "$NODE_ROOT/node.pid" ]]; then
    read -r pid < "$NODE_ROOT/node.pid"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null && [[ "$(readlink -f "/proc/$pid/exe" 2>/dev/null)" == "$(readlink -f "$NODE_EXE")" ]]; then owned=true; fi
  fi
  if [[ "$owned" == false ]]; then
    if command -v ss >/dev/null && ss -ltn | awk '{print $4}' | grep -Eq ':20001$'; then
      echo 'P2P port 20001 is occupied; refusing to start another node while RPC is unavailable' >&2
      exit 1
    fi
    nohup "$NODE_EXE" --port 20001 --datadir "$NODE_ROOT/data" >>"$NODE_ROOT/node-console.log" 2>&1 </dev/null 8>&- 9>&- &
    printf '%s\n' "$!" > "$NODE_ROOT/node.pid"
  fi
  for ((i=0;i<90;i++)); do
    sleep 1
    if curl --fail --silent --max-time 2 "$NODE_URL/api/get_info" >/dev/null 2>&1; then exit 0; fi
  done
  echo "Node RPC unavailable; inspect $NODE_ROOT/node-console.log" >&2
  exit 1
fi
