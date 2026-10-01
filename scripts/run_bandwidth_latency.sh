#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
source scripts/lib_storage.sh
RESULTS_ROOT="$(resolve_results_root)"

BINARY="$PROJECT_ROOT/src/level-zero-tests/out/ze_peer"
if [[ ! -x "$BINARY" ]]; then
    echo "Missing $BINARY. Run scripts/build.sh first." >&2
    exit 1
fi

# Keep these fixed across PCIe configurations for comparable results.
SRC="${ZE_PEER_SRC:-0}"
DST="${ZE_PEER_DST:-1}"
ITERS="${ZE_PEER_ITERS:-50}"
CONFIG_NAME="${CONFIG_NAME:-unnamed}"
RUNS="${RUNS:-1}"
if ! [[ "$RUNS" =~ ^[0-9]+$ ]] || [[ "$RUNS" -lt 1 ]]; then
    echo "RUNS must be a positive integer, got '$RUNS'" >&2
    exit 1
fi

for ((run = 1; run <= RUNS; run++)); do
    RUN_ID="$(date +%Y%m%d-%H%M%S)_zepeer_${CONFIG_NAME}"
    OUTPUT_DIR="$RESULTS_ROOT/$RUN_ID"
    mkdir -p "$OUTPUT_DIR"

    {
        echo "timestamp_utc=$(date --utc +%FT%TZ)"
        echo "config_name=$CONFIG_NAME"
        echo "src_device=$SRC"
        echo "dst_device=$DST"
        printf 'command=%q -s %q -d %q -i %q\n' "$BINARY" "$SRC" "$DST" "$ITERS"
        lspci -d 8086:e223 2>&1
        xpu-smi discovery 2>&1 || true
    } >"$OUTPUT_DIR/environment.txt"

    echo "Running ze_peer bandwidth+latency sweep for configuration: $CONFIG_NAME (run $run/$RUNS)"
    "$BINARY" -s "$SRC" -d "$DST" -i "$ITERS" 2>&1 | tee "$OUTPUT_DIR/ze_peer_8B_to_256MB.txt"
    echo "Results saved in $OUTPUT_DIR"
done
