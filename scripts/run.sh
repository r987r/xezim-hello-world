#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
XEZIM_VERSION="${XEZIM_VERSION:-0.11.3}"
XEZIM_DIR="${XEZIM_DIR:-$ROOT/.tools/xezim}"
XEZIM_BIN="${XEZIM_BIN:-$XEZIM_DIR/target/release/xezim}"

if [[ ! -x "$XEZIM_BIN" ]]; then
    if ! command -v git >/dev/null 2>&1; then
        echo 'ERROR: git is required to fetch the Xezim source.' >&2
        exit 1
    fi
    if ! command -v cargo >/dev/null 2>&1; then
        echo 'ERROR: Rust 1.92+ and Cargo are required to build Xezim.' >&2
        exit 1
    fi
    if [[ ! -f "$XEZIM_DIR/Cargo.toml" ]]; then
        echo "Fetching Xezim $XEZIM_VERSION ..."
        mkdir -p "$(dirname "$XEZIM_DIR")"
        git clone --depth 1 --branch "$XEZIM_VERSION" https://github.com/aionhw/xezim.git "$XEZIM_DIR"
    fi
    echo 'Building Xezim (release mode) ...'
    CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-1}" \
    CARGO_PROFILE_RELEASE_LTO="${CARGO_PROFILE_RELEASE_LTO:-false}" \
    CARGO_PROFILE_RELEASE_CODEGEN_UNITS="${CARGO_PROFILE_RELEASE_CODEGEN_UNITS:-16}" \
    CARGO_PROFILE_RELEASE_OPT_LEVEL="${CARGO_PROFILE_RELEASE_OPT_LEVEL:-1}" \
    CARGO_PROFILE_RELEASE_DEBUG="${CARGO_PROFILE_RELEASE_DEBUG:-0}" \
        cargo build --release --bin xezim --manifest-path "$XEZIM_DIR/Cargo.toml"
fi

LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT
echo 'Compiling, elaborating, and simulating the Hello World testbench ...'
"$XEZIM_BIN" -s hello_world_tb "$ROOT/rtl/hello_world.sv" "$ROOT/tb/hello_world_tb.sv" 2>&1 | tee "$LOG"
if ! grep -Fxq 'PASS: hello_world_tb' "$LOG"; then
    echo 'ERROR: Xezim did not produce the expected PASS marker.' >&2
    exit 1
fi
