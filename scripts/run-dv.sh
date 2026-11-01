#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -n "${XEZIM_BIN:-}" ]]; then
  if [[ ! -x "$XEZIM_BIN" ]]; then
    echo "XEZIM_BIN is not executable: $XEZIM_BIN" >&2; exit 1
  fi
elif [[ -x "$ROOT/.tools/xezim/target/release/xezim" ]]; then
  XEZIM_BIN="$ROOT/.tools/xezim/target/release/xezim"
elif command -v xezim >/dev/null 2>&1; then
  XEZIM_BIN="$(command -v xezim)"
else
  echo 'Xezim executable missing. Set XEZIM_BIN or add xezim to PATH.' >&2
  echo 'SystemVerilog DV deliberately never compiles the simulator itself.' >&2
  exit 1
fi

python3 tools/socgen.py

vendor="$ROOT/.tools/verilog-axi"
rev="$(python3 - <<'PY'
import yaml
with open('config/ip.lock.yaml') as f: print(yaml.safe_load(f)['third_party']['verilog_axi']['commit'])
PY
)"
if [[ ! -d "$vendor/.git" ]]; then
  mkdir -p "$ROOT/.tools"
  git init -q "$vendor"
  git -C "$vendor" remote add origin https://github.com/alexforencich/verilog-axi.git
fi
if [[ "$(git -C "$vendor" rev-parse HEAD 2>/dev/null || true)" != "$rev" ]]; then
  git -C "$vendor" fetch -q --depth 1 origin "$rev"
  git -C "$vendor" -c advice.detachedHead=false checkout -q --detach "$rev"
fi

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
  "$ROOT/dv/common/axi_master_bfm.sv"
  "$ROOT/dv/common/axi_route_monitor.sv"
  "$ROOT/generated/hbm/hbm_tb.sv"
)
for file in "${files[@]}"; do
  if [[ ! -s "$file" ]]; then echo "Missing source $file" >&2; exit 1; fi
done

args=("--max-time" "200us" "-s" "hbm_tb" "${files[@]}")
if [[ "${1:-}" == "--negative" ]]; then
  args+=("+INJECT_BAD_EXPECTED")
fi
"$XEZIM_BIN" "${args[@]}"
