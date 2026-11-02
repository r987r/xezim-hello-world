#!/usr/bin/env bash
# Cross-simulator compile *the same* FlooGen RTL source/top that Verilator uses.
# Diagnostic only: no pretend AXI stimulus, no custom FlooNoC modules.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
: "${XEZIM_BIN:?Set XEZIM_BIN to pinned xezim-linux-x86_64 executable}"
filelist="${FLOONOC_FILELIST:-$ROOT/.tools/floonoc-lint.f}"
if [[ ! -s "$filelist" ]]; then
  echo "Missing upstream Bender FlooNoC source filelist: $filelist" >&2
  exit 2
fi
mapfile -t sources < <(grep -E '\.(sv|v)$' "$filelist")
[[ ${#sources[@]} -gt 0 ]] || { echo "No upstream RTL in filelist" >&2; exit 2; }
includes=()
for dir in "$ROOT"/.tools/floonoc/.bender/git/checkouts/*/include "$ROOT/.tools/floonoc/hw/include"; do
  [[ -d "$dir" ]] && includes+=("-I$dir")
done
for network in "${@:-global_data}"; do
  case "$network" in
    global_data|global_config) ;;
    *) echo "Supported NoC probe names: global_data, global_config" >&2; exit 2 ;;
  esac
  prefix="$ROOT/gen/noc/floonoc/$network/floo_xezim_${network}_noc"
  top="floo_xezim_${network}_noc"
  [[ -s "${prefix}_pkg.sv" && -s "${prefix}.sv" ]] || exit 2
  echo "XEZIM compile probe: $top (same Bender-pinned network as Verilator)"
  "$XEZIM_BIN" --compile --no-cache -s "$top" "${includes[@]}" \
    "${sources[@]}" "${prefix}_pkg.sv" "${prefix}.sv"
done
