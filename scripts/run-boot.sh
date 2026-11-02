#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
cd "$ROOT"
python3 tools/generate.py --check
python3 tools/ip_fetch.py picorv32 serv
mapfile -t serv_sources < <(python3 - <<'PY'
import yaml
from pathlib import Path
lock = yaml.safe_load(Path("config/ip.lock.yaml").read_text())
for module in lock["third_party"]["serv"]["modules"]:
    print(str(Path(".tools/serv") / module))
PY
)
sources=("$ROOT/.tools/picorv32/picorv32.v" "${serv_sources[@]}")
sources+=("$ROOT/rtl/adapters/picorv32_cpu_adapter.sv" "$ROOT/rtl/adapters/serv_cpu_adapter.sv"
          "$ROOT/rtl/interconnect/boot_local_decode.sv" "$ROOT/rtl/memory/local_sram.sv" "$ROOT/rtl/boot/boot_memory_model.sv" "$ROOT/dv/boot/boot_tb.sv")
args=(--max-time 1500us -s boot_tb)
if [[ "${BOOT_WAVE:-0}" == "1" ]]; then args+=(--wave +BOOT_WAVE); fi
if [[ "${BOOT_TRACE:-0}" == "1" ]]; then args+=(+BOOT_TRACE); fi
"$XEZIM_BIN" "${args[@]}" "${sources[@]}"
