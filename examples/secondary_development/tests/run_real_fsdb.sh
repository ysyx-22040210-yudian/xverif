#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
example_root="$(cd "$script_dir/.." && pwd)"
fixture="$example_root/fixtures/fsdb_handshake"
fsdb="$fixture/waves.fsdb"
manifest="$fixture/signal_manifest.json"

if [[ -n "${KVERIF_JSON_PYTHON:-}" ]]; then
  json_python="$KVERIF_JSON_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  json_python=python3
else
  json_python=python
fi

if [[ -n "${KDEBUG_BIN:-}" ]]; then
  kdebug="$KDEBUG_BIN"
elif [[ -n "${KVERIF_HOME:-}" && -x "$KVERIF_HOME/tools/kdebug" ]]; then
  kdebug="$KVERIF_HOME/tools/kdebug"
elif [[ -x "$example_root/../../tools/kdebug" ]]; then
  kdebug="$example_root/../../tools/kdebug"
else
  kdebug="$(command -v kdebug 2>/dev/null || true)"
fi

[[ -n "$kdebug" && -x "$kdebug" ]] || {
  echo "ERROR: cannot find kdebug; set KDEBUG_BIN or KVERIF_HOME" >&2
  exit 2
}
[[ -s "$fsdb" && -f "$manifest" ]] || {
  echo "ERROR: bundled FSDB fixture is incomplete: $fixture" >&2
  exit 2
}

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

"$json_python" - "$manifest" "$fsdb" <<'PY'
import hashlib
import json
import os
import sys

manifest_path, fsdb_path = sys.argv[1:]
with open(manifest_path, encoding="utf-8") as stream:
    manifest = json.load(stream)
with open(fsdb_path, "rb") as stream:
    digest = hashlib.sha256(stream.read()).hexdigest()
assert os.path.getsize(fsdb_path) == manifest["artifact"]["size_bytes"]
assert digest == manifest["artifact"]["sha256"]
print("ARTIFACT_OK", digest)
PY

"$json_python" - "$manifest" >"$tmp_dir/signals.tsv" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    manifest = json.load(stream)
for item in manifest["signals"]:
    print("{0}\t{1}".format(item["name"], item["expected_change_count"]))
PY

while IFS=$'\t' read -r signal expected_changes; do
  "$kdebug" --json action signal.scan \
    --fsdb "$fsdb" \
    --arg "signal=$signal" --arg begin=0ns --arg end=125ns \
    --arg format=hex --max-rows 100 >"$tmp_dir/scan.json"
  "$json_python" - "$signal" "$expected_changes" "$tmp_dir/scan.json" <<'PY'
import json
import sys

signal, expected_changes, response_path = sys.argv[1:]
with open(response_path, encoding="utf-8") as stream:
    response = json.load(stream)
assert response.get("ok") is True, response
summary = response["summary"]
assert summary["signal"] == signal, summary
assert summary["change_count"] == int(expected_changes), summary
assert summary["truncated"] is False, summary
print("SCAN_OK", signal, "changes=" + expected_changes)
PY
done <"$tmp_dir/signals.tsv"

"$json_python" - "$manifest" >"$tmp_dir/checkpoints.tsv" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    manifest = json.load(stream)
for item in manifest["checkpoints"]:
    values = item["expected"]
    print(
        "{0}\t{1}\t{2}".format(
            item["time"],
            values["tb_kverif_handshake.dut.accepted_count"],
            values["tb_kverif_handshake.dut.rsp_data"],
        )
    )
PY

while IFS=$'\t' read -r sample_time expected_count expected_data; do
  "$kdebug" --json value-batch \
    --fsdb "$fsdb" \
    --signal tb_kverif_handshake.dut.accepted_count \
    --signal tb_kverif_handshake.dut.rsp_data \
    --time "$sample_time" --format hex >"$tmp_dir/value.json"
  "$json_python" - "$sample_time" "$expected_count" "$expected_data" \
    "$tmp_dir/value.json" <<'PY'
import json
import sys

sample_time, expected_count, expected_data, response_path = sys.argv[1:]
with open(response_path, encoding="utf-8") as stream:
    response = json.load(stream)
assert response.get("ok") is True, response
values = {item["signal"]: item["raw"].lower() for item in response["data"]["values"]}
assert values["tb_kverif_handshake.dut.accepted_count"] == expected_count, values
assert values["tb_kverif_handshake.dut.rsp_data"] == expected_data, values
print("CHECKPOINT_OK", sample_time, "count=" + expected_count, "data=" + expected_data)
PY
done <"$tmp_dir/checkpoints.tsv"

common=(
  --fsdb "$fsdb"
  --signal tb_kverif_handshake.dut.accepted_count
  --begin 0ns --end 125ns
  --min-changes 5 --max-unknown 0 --require-complete
)

KDEBUG_BIN="$kdebug" KVERIF_JSON_PYTHON="$json_python" \
  bash "$example_root/sh/signal_health.sh" \
  "${common[@]}" --out "$tmp_dir/signal-health-sh"

KDEBUG_BIN="$kdebug" KVERIF_JSON_PYTHON="$json_python" \
  perl "$example_root/perl/signal_health.pl" \
  "${common[@]}" --out "$tmp_dir/signal-health-perl"

KDEBUG_BIN="$kdebug" \
  "$json_python" "$example_root/py/signal_health.py" \
  "${common[@]}" --out "$tmp_dir/signal-health-python"

if command -v csh >/dev/null 2>&1; then
  KDEBUG_BIN="$kdebug" KVERIF_JSON_PYTHON="$json_python" \
    csh "$example_root/csh/signal_health.csh" \
    "${common[@]}" --out "$tmp_dir/signal-health-csh"
fi

KDEBUG_BIN="$kdebug" KVERIF_JSON_PYTHON="$json_python" \
  bash "$example_root/sh/waveform_window.sh" \
    --fsdb "$fsdb" \
    --signal tb_kverif_handshake.dut.req_valid \
    --signal tb_kverif_handshake.dut.req_ready \
    --signal tb_kverif_handshake.dut.req_fire \
    --signal tb_kverif_handshake.dut.rsp_data \
    --begin 0ns --end 125ns --time 45ns --time 95ns \
    --min-changes 2 --max-unknown 0 --require-complete \
    --out "$tmp_dir/waveform-window"

test -s "$tmp_dir/waveform-window/report.json"
echo "PASS: real bundled FSDB and secondary-development examples"
