#!/usr/bin/env bash
stats=$(curl --max-time 3 -sf http://127.0.0.1:8808/api/status) || stats='{}'
khs=$(jq -r '(.hashrate // 0) / 1000' <<< "$stats")
stats=$(jq -c '. as $s | {hs: [(.devices // {} | to_entries[] | if $s.state=="Mining" then .value.hashrate // 0 else 0 end)],hs_units:"hs",temp:[(.devices // {} | to_entries[] | .value.temperature_c)],fan:[(.devices // {} | to_entries[] | .value.fan_percent)],power:[(.devices // {} | to_entries[] | .value.power_w)],ar:[(.accepted // 0),(.rejected // 0)],ver:"0.1.0",algo:"sha256-json"}' <<< "$stats")
