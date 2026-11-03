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
# NoC top names, generated packages and paths are read from the actual
# FlooGen manifest, so extra compute or memory subsystems need no script edits.
mapfile -t profiles < <(python3 - "$@" <<'PY'
import json
from pathlib import Path
import sys
root = Path("gen/noc/floonoc")
entries = json.loads((root / "manifest.json").read_text())["networks"]
wanted = sys.argv[1:]
if not wanted or wanted == ["all"]:
    wanted = sorted(entries)
for name in wanted:
    if name not in entries:
        raise SystemExit(f"Unknown FlooNoC network {name}; choices: {sorted(entries)}")
    entry = entries[name]
    print(" ".join([name, entry["top_module"],
                    str(root / entry["package"]), str(root / entry["top"])]))
PY
)
[[ ${#profiles[@]} -gt 0 ]] || { echo "No FlooNoC profiles" >&2; exit 2; }
for profile in "${profiles[@]}"; do
  read -r network top package rtl <<< "$profile"
  [[ -s "$package" && -s "$rtl" ]] || {
    echo "Missing generated NoC package or top: $profile" >&2
    exit 2
  }
  echo "XEZIM compile probe: $top (same Bender-pinned source list as Verilator)"
  transcript="$ROOT/.tools/xezim-${network}-compile.log"
  "$XEZIM_BIN" --compile --no-cache -s "$top" "${includes[@]}" \
    "${sources[@]}" "$package" "$rtl" 2>&1 | tee "$transcript"
  warnings="$(grep -cF '[xezim][warning]' "$transcript" || true)"
  echo "PASS Xezim compiled $network; emitted $warnings warning lines (diagnostic output is capped by Xezim)"
done
echo "PASS Xezim compiled ${#profiles[@]} source-controlled FlooNoC modules"
