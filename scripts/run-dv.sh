#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
cd "$ROOT"
python3 tools/socgen.py
python3 tools/ip_fetch.py verilog_axi
vendor="$ROOT/.tools/verilog_axi"
files=(
  "$vendor/rtl/priority_encoder.v"
  "$vendor/rtl/arbiter.v"
  "$vendor/rtl/axi_crossbar_addr.v"
  "$vendor/rtl/axi_register_wr.v"
  "$vendor/rtl/axi_register_rd.v"
  "$vendor/rtl/axi_crossbar_wr.v"
  "$vendor/rtl/axi_crossbar_rd.v"
  "$vendor/rtl/axi_crossbar.v"
  "$vendor/rtl/axi_ram.v"
  "$ROOT/rtl/adapters/axi_memory_target_model.sv"
  "$ROOT/dv/common/axi_master_bfm.sv"
  "$ROOT/dv/common/axi_route_monitor.sv"
  "$ROOT/generated/memory/memory_tb.sv"
)
for file in "${files[@]}"; do
  [[ -s "$file" ]] || { echo "Missing RTL source: $file" >&2; exit 1; }
done
args=("--max-time" "200us" "-s" "memory_tb" "${files[@]}")
if [[ "${1:-}" == "--negative" ]]; then args+=("+INJECT_BAD_EXPECTED"); fi
"$XEZIM_BIN" "${args[@]}"
