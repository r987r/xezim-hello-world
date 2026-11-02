#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
cd "$ROOT"
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
sources+=("$ROOT/rtl/adapters/picorv32_cpu_adapter.sv" "$ROOT/rtl/adapters/serv_cpu_adapter.sv" "$ROOT/dv/cpu/heterogeneous_cpu_tb.sv")
"$XEZIM_BIN" -D SERV_CLEAR_RAM --max-time 20us -s heterogeneous_cpu_tb "${sources[@]}"
