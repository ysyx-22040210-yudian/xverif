#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: build_vcs.sh [--out DIR]

Compile the bundled RTL/testbench with VCS and generate waves.fsdb.
The output directory defaults to fixtures/fsdb_handshake/build.

Environment:
  VCS             Optional VCS executable; defaults to vcs from PATH.
  VCS_OPTS        Optional additional VCS options.
  VCS_TARGET_ARCH Usually linux64 for Synopsys 2018 installations.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out_dir="$script_dir/build"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) out_dir="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -n "${VCS:-}" ]]; then
  vcs_bin="$VCS"
else
  vcs_bin="$(command -v vcs 2>/dev/null || true)"
fi
[[ -n "$vcs_bin" ]] || {
  echo "ERROR: VCS is not available; set VCS or add vcs to PATH" >&2
  exit 2
}

mkdir -p "$out_dir"
out_dir="$(cd "$out_dir" && pwd)"

vcs_command=(
  "$vcs_bin"
  -full64 -sverilog -timescale=1ns/1ps
  -debug_access+all -kdb -lca
)
if [[ -n "${VCS_OPTS:-}" ]]; then
  # VCS_OPTS is an operator-controlled build setting, so shell word splitting is intentional.
  # shellcheck disable=SC2206
  split_opts=($VCS_OPTS)
  vcs_command+=("${split_opts[@]}")
fi

vcs_command+=(
  "$script_dir/rtl/kverif_handshake_dut.sv"
  "$script_dir/tb/tb_kverif_handshake.sv"
  -top tb_kverif_handshake
  -o "$out_dir/simv"
  -l "$out_dir/compile.log"
)
"${vcs_command[@]}"

(
  cd "$out_dir"
  ./simv -l run.log
)

[[ -s "$out_dir/waves.fsdb" ]] || {
  echo "ERROR: simulation completed without a non-empty waves.fsdb" >&2
  exit 1
}

printf 'FSDB generated: %s\n' "$out_dir/waves.fsdb"
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$out_dir/waves.fsdb"
fi
