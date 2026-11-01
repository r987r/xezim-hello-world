#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
cd "$ROOT"
python3 tools/ip_fetch.py picorv32 serv
mapfile -t serv_modules < <(python3 - <<'PY'
import yaml
with open('config/ip.lock.yaml') as f: print('\n'.join(yaml.safe_load(f)['third_party']['serv']['modules']))
PY
)
sources=("$ROOT/.tools/picorv32/picorv32.v")
for file in "${serv_modules[@]}"; do sources+=("$ROOT/.tools/serv/$file"); done
sources+=("$ROOT/rtl/adapters/picorv32_cpu_adapter.sv" "$ROOT/rtl/adapters/serv_cpu_adapter.sv" "$ROOT/dv/cpu/heterogeneous_cpu_tb.sv")
"$XEZIM_BIN" --max-time 20us -s heterogeneous_cpu_tb "${sources[@]}"
