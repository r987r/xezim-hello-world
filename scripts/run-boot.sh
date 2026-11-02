#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
cd "$ROOT"
python3 tools/generate.py --check
python3 tools/ip_fetch.py picorv32 serv
serv_files="$(python3 tools/serv_compat.py)"
mapfile -t serv_sources <<< "$serv_files"
sources=("$ROOT/.tools/picorv32/picorv32.v" "${serv_sources[@]}")
sources+=("$ROOT/rtl/adapters/picorv32_cpu_adapter.sv" "$ROOT/rtl/adapters/serv_cpu_adapter.sv"
          "$ROOT/rtl/boot/boot_memory_model.sv" "$ROOT/dv/boot/boot_tb.sv")
args=(-D SERV_CLEAR_RAM --max-time 1500us -s boot_tb)
if [[ "${BOOT_WAVE:-0}" == "1" ]]; then args+=(--wave +BOOT_WAVE); fi
if [[ "${BOOT_TRACE:-0}" == "1" ]]; then args+=(+BOOT_TRACE); fi
"$XEZIM_BIN" "${args[@]}" "${sources[@]}"
