# PCIe ZePeer Benchmarks

Reproducible Intel Arc GPU-to-GPU PCIe peer-to-peer microbenchmarks for this workstation,
using Intel's official `ze_peer` tool from the
[oneAPI Level Zero Tests](https://github.com/oneapi-src/level-zero-tests) repo. This is the
Level-Zero/Arc analogue of [PCIe NCCL Benchmarks](../PCIe%20NCCL%20Benchmarks/README.md)'s
`nccl-tests` -- same goal (compare PCIe configurations), different hardware stack: this
repo measures raw point-to-point copy bandwidth/latency instead of NCCL collectives, since
there's no off-the-shelf NCCL-equivalent all-reduce microbenchmark tool for the `xccl`/oneCCL
backend yet (oneCCL's own `examples/benchmark` would need to be built from source separately --
see "Future possibility" below).

This project builds `ze_peer` directly against the system's Level Zero loader
(`libze-dev`), so it does **not** need the `vllm-xpu` conda environment -- it only needs a
few system packages.

## First build

```bash
cd "/home/intel/PCIe ZePeer Benchmarks"
sudo apt-get install -y cmake libpng-dev libboost-all-dev libva-dev libze-dev
./scripts/build.sh
```

`build.sh` clones `oneapi-src/level-zero-tests` and builds just the performance tests
(`-DBUILD_ZE_PERF_TESTS_ONLY=YES`) under `src/level-zero-tests/build/`, installing the
`ze_peer` binary to `src/level-zero-tests/out/ze_peer`. Override the source ref with
`LZT_REF=<tag-or-branch> ./scripts/build.sh` when needed.

Note: this system's Boost (1.88) is older than the 1.92 some *other* perf tests in that repo
want (`ze_nano`, `ze_image_copy`) -- those are skipped automatically. `ze_peer` itself has no
such requirement and builds fine.

## Bandwidth + latency sweep

```bash
./scripts/run_bandwidth_latency.sh
```

This runs `ze_peer` between device 0 and device 1 (the two Arc B70s) over its full default
sweep -- unidirectional write and read, both bandwidth and latency, for sizes from 8 B through
256 MB. A full sweep takes a few seconds. Results and the exact topology/environment are stored
in `results/<UTC timestamp>_zepeer_<CONFIG_NAME>/`.

Override defaults with environment variables:

```bash
CONFIG_NAME=node_x16 ZE_PEER_ITERS=50 RUNS=3 ./scripts/run_bandwidth_latency.sh
```

- `CONFIG_NAME` identifies the physical configuration in the result directory name (default: `unnamed`).
- `ZE_PEER_SRC` / `ZE_PEER_DST` select which Level-Zero device indices to test (default: `0` / `1`). Use `src/level-zero-tests/out/ze_peer -q` to list detected devices.
- `ZE_PEER_ITERS` sets iterations per size (default: 50).
- `RUNS` repeats the sweep back-to-back under the same `CONFIG_NAME`, each producing its own timestamped result directory (default: 1).

Repeat at least three times per physical configuration when comparing small differences, same
as the NCCL repo's guidance. Keep the GPU pair, clocks, power limits, and driver unchanged
between configurations being compared.

## Results dashboard

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

The dashboard overlays individual runs and per-size medians for bandwidth and latency (both
read and write directions), then summarizes representative sizes for every selected
configuration.

## Storage location

Results are written to `results/` inside the repo by default, so a fresh clone works with no
setup. To point at a shared/network location instead, copy `.storage-config.example` to
`.storage-config` (gitignored) and set the path there, or set the `ZE_PEER_RESULTS_DIR`
environment variable. Precedence: env var > `.storage-config` > `results/`.

## Future possibility: real oneCCL collective benchmark

`ze_peer` measures raw point-to-point copies, not collective operations (all-reduce, etc.) --
it's a different scenario than the NCCL repo's `all_reduce_perf`, but still useful for comparing
PCIe configurations since it stresses the same physical link. For a true NCCL-equivalent
all-reduce benchmark on this stack, oneCCL's own `examples/benchmark` would need to be built
from the [oneCCL source](https://github.com/oneapi-src/oneCCL) (the pip `oneccl`/`oneccl-devel`
packages used by vLLM only ship runtime libraries, not the benchmark example) -- left as a
follow-up, not implemented here.
