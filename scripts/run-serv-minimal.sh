#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
cd "$ROOT"
python3 tools/ip_fetch.py serv
mapfile -t sources < <(python3 - <<'PY'
import yaml
from pathlib import Path
lock = yaml.safe_load(Path("config/ip.lock.yaml").read_text())
for module in lock["third_party"]["serv"]["modules"]:
    print(str(Path(".tools/serv") / module))
PY
)
sources+=("$ROOT/rtl/adapters/serv_cpu_adapter.sv" "$ROOT/dv/cpu/serv_minimal_tb.sv")
"$XEZIM_BIN" --no-cache --max-time 40us -s serv_minimal_tb "${sources[@]}"
