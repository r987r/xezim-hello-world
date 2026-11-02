#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
cd "$ROOT"
python3 tools/ip_fetch.py serv
serv_files="$(python3 tools/serv_compat.py)"
mapfile -t sources <<< "$serv_files"
sources+=("$ROOT/rtl/adapters/serv_cpu_adapter.sv" "$ROOT/dv/cpu/serv_minimal_tb.sv")
"$XEZIM_BIN" --no-cache -D SERV_CLEAR_RAM --max-time 40us -s serv_minimal_tb "${sources[@]}"
