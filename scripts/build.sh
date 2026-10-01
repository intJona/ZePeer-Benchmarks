#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

LZT_REF="${LZT_REF:-master}"
SRC_DIR="src/level-zero-tests"
BUILD_DIR="$SRC_DIR/build"

if [[ ! -d "$SRC_DIR/.git" ]]; then
    echo "Fetching level-zero-tests ($LZT_REF)..."
    git clone --depth 1 --branch "$LZT_REF" https://github.com/oneapi-src/level-zero-tests.git "$SRC_DIR"
fi

mkdir -p "$BUILD_DIR"
cmake -S "$SRC_DIR" -B "$BUILD_DIR" \
    -D CMAKE_BUILD_TYPE=Release \
    -D CMAKE_INSTALL_PREFIX="$PROJECT_ROOT/$SRC_DIR/out" \
    -D BUILD_ZE_PERF_TESTS_ONLY=YES
cmake --build "$BUILD_DIR" --config Release --target install -- -j"$(nproc)"

echo "Built: $PROJECT_ROOT/$SRC_DIR/out/ze_peer"
