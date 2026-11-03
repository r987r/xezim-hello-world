#!/usr/bin/env bash
# One integrated eight-FlooNoC traffic regression, with real upstream PULP AXI VIP.
# Requires Bender-resolved FlooNoC dependencies (.tools/floonoc-lint.f) and Verilator.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
test -s gen/supernoc/supernoc_tb.sv
test -s .tools/floonoc-lint.f
axi_test="$(find .tools/floonoc/.bender/git/checkouts -path '*/src/axi_test.sv' -print -quit)"
axi_intf="$(find .tools/floonoc/.bender/git/checkouts -path '*/src/axi_intf.sv' -print -quit)"
if [[ ! -s "$axi_test" || ! -s "$axi_intf" ]]; then
  echo "Missing locked upstream PULP axi_test.sv/axi_intf.sv (Bender checkout)" >&2
  exit 2
fi
includes=()
for d in .tools/floonoc/.bender/git/checkouts/*/include .tools/floonoc/hw/include; do
  [[ -d "$d" ]] && includes+=("-I$d")
done
mapfile -t noc_sv < <(python3 - <<'PY'
import json
from pathlib import Path
p=Path("gen/noc/floonoc")
m=json.loads((p/"manifest.json").read_text())["networks"]
for _, x in sorted(m.items()):
    print(p/x["package"])
for _, x in sorted(m.items()):
    print(p/x["top"])
PY
)
filelist=".tools/floonoc-lint.f"
# Upstream RTL dependency order must remain determined by FlooNoC Bender.lock.
if grep -qF "$axi_intf" "$filelist" || grep -q '/src/axi_intf[.]sv' "$filelist"; then
  extra_intf=()
else
  extra_intf=("$axi_intf")
fi
sources=("-f" "$filelist" "${extra_intf[@]}" "$axi_test" "${noc_sv[@]}" "gen/supernoc/supernoc_tb.sv")
verilator --lint-only --timing --assert -Wno-fatal --top-module supernoc_tb \
  "${includes[@]}" "${sources[@]}"
echo "PASS: all eight FlooNoC instances and PULP AXI BFM interfaces linted"
if [[ "${SUPER_NOC_LINT_ONLY:-0}" == "1" ]]; then exit 0; fi
verilator --binary --timing --assert -Wno-fatal -j 2 \
  --Mdir .tools/supernoc-obj --top-module supernoc_tb \
  "${includes[@]}" "${sources[@]}"
timeout 180s .tools/supernoc-obj/Vsupernoc_tb | tee supernoc-dv.log
grep -q 'PASS supernoc:' supernoc-dv.log
echo "PASS: end-to-end directed AXI read/write readback across real local/global FlooNoCs"
