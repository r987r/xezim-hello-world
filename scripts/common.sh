#!/usr/bin/env bash
# Shared simulator selection. HDL tests never compile Rust/Xezim.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${XEZIM_BIN:-}" ]]; then
    [[ -x "$XEZIM_BIN" ]] || { echo "XEZIM_BIN not executable: $XEZIM_BIN" >&2; exit 1; }
elif [[ -x "$ROOT/.tools/bin/xezim-linux-x86_64" ]]; then
    XEZIM_BIN="$ROOT/.tools/bin/xezim-linux-x86_64"
elif command -v xezim >/dev/null 2>&1; then
    XEZIM_BIN="$(command -v xezim)"
else
    echo 'Xezim executable missing; set XEZIM_BIN or add xezim to PATH.' >&2
    exit 1
fi
export XEZIM_BIN
