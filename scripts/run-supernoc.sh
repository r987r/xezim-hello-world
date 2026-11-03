#!/usr/bin/env bash
# Single full-SoC NoC traffic test: real FlooGen meshes and cocotbext-axi BFMs.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
test -s gen/supernoc/supernoc_tb.sv
test -s gen/supernoc/manifest.json
test -s .tools/floonoc-lint.f
python3 dv/supernoc/run.py 2>&1 | tee supernoc-dv.log
grep -q 'PASS supernoc:' supernoc-dv.log
