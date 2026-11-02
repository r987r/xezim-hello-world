#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
cd "$ROOT"
"$XEZIM_BIN" --max-time 10us -s local_sram_tb rtl/memory/local_sram.sv dv/memory/local_sram_tb.sv
