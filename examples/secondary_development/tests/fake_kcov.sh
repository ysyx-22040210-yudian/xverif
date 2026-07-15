#!/usr/bin/env bash
set -euo pipefail

all_args=" $* "
vdb=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "--vdb" && $# -gt 1 ]]; then
    vdb="$2"
    shift 2
  else
    shift
  fi
done

covered=70
[[ "$vdb" != *run2* ]] || covered=82
missing=$((100 - covered))
if [[ "$all_args" == *" cov-holes "* ]]; then
  holes=30
  [[ "$vdb" != *run2* ]] || holes=18
  printf '{"api_version":"kcov.v1","action":"cov.holes","ok":true,'
  printf '"summary":{"fake":true,"matched_count":%d},"data":{"items":[]}}\n' "$holes"
else
  printf '{"api_version":"kcov.v1","action":"cov.summary","ok":true,'
  printf '"summary":{"fake":true},"data":{"items":['
  printf '{"metric":"line","covered":%d,"coverable":100,"missing":%d,"coverage_pct":%d}' \
    "$covered" "$missing" "$covered"
  printf ']}}\n'
fi
