#!/usr/bin/env python3
"""Interactive comparison dashboard for saved ze_peer P2P bandwidth/latency sweeps."""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from pathlib import Path
from statistics import median

import plotly.graph_objects as go
import streamlit as st

import cache_store

REPO_ROOT = Path(__file__).resolve().parent


def resolve_results_root() -> Path:
    """Results dir: $ZE_PEER_RESULTS_DIR, then .storage-config, then ./results."""
    env_override = os.environ.get("ZE_PEER_RESULTS_DIR")
    if env_override:
        return Path(env_override).expanduser()
    config_file = REPO_ROOT / ".storage-config"
    if config_file.exists():
        for line in config_file.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                return Path(line).expanduser()
    return REPO_ROOT / "results"


RESULTS_ROOT = resolve_results_root()
RESULT_FILE_GLOB = "ze_peer_*.txt"
UNIT_BYTES = {"B": 1, "KB": 1024, "MB": 1024 * 1024}
SECTION_HEADER = re.compile(r"^(Bandwidth|Latency) (Write|Read) : Device\(\s*\d+\s*\)(?:->|<-)Device\(\s*\d+\s*\)")
DATA_LINE = re.compile(r"^(BW \[GBPS\]|Latency \[us\]):\s+([\d.]+)\s*(B|KB|MB):\s+([\d.]+)")
# Okabe-Ito palette: distinguishable under deuteranopia/protanopia/tritanopia.
PALETTE = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#000000"]
DASH_STYLES = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"]
MARKER_SYMBOLS = ["circle", "square", "diamond", "triangle-up", "x", "star", "triangle-down", "pentagon"]


def read_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in path.read_text(errors="replace").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
    except OSError:
        pass
    return values


def parse_result(path: Path) -> list[dict]:
    rows = []
    direction = None
    try:
        content = path.read_text(errors="replace")
    except OSError:
        return rows
    for line in content.splitlines():
        line = line.strip()
        header_match = SECTION_HEADER.match(line)
        if header_match:
            direction = header_match.group(2).lower()
            continue
        data_match = DATA_LINE.match(line)
        if data_match and direction:
            metric_label, size, unit, value = data_match.groups()
            metric = "bw_gbps" if metric_label.startswith("BW") else "latency_us"
            rows.append({
                "size": float(size) * UNIT_BYTES[unit],
                "direction": direction,
                "metric": metric,
                "value": float(value),
            })
    return rows


@st.cache_data(show_spinner=False)
def discover_runs() -> list[dict]:
    runs = []
    if not RESULTS_ROOT.exists():
        return runs
    for result_file in sorted(RESULTS_ROOT.glob(f"*/{RESULT_FILE_GLOB}")):
        rows = parse_result(result_file)
        if not rows:
            continue
        run_dir = result_file.parent
        environment = read_environment(run_dir / "environment.txt")
        config = environment.get("config_name") or "unlabelled"
        runs.append({
            "id": run_dir.name,
            "config": config,
            "rows": rows,
            "environment": environment,
            "file": result_file.name,
        })
    return runs


@st.cache_data(show_spinner=False)
def discover_skipped_results() -> list[str]:
    skipped = []
    if not RESULTS_ROOT.exists():
        return skipped
    for result_file in sorted(RESULTS_ROOT.glob(f"*/{RESULT_FILE_GLOB}")):
        if not parse_result(result_file):
            skipped.append(str(result_file))
    return skipped


FIRST_SCAN_NOTICE = ("No cached data found yet. The first scan has to walk the results directory over the network "
    "share and can take a minute or more depending on how many runs are present.")
REFRESH_NOTICE = "Rescanning RESULTS_ROOT over the network share -- this can take a minute or more."


def get_runs(force_refresh: bool = False) -> tuple[list[dict], dict | None, bool]:
    """Load runs from cache or re-scan. Returns (runs, meta, was_cached)."""
    runs, meta = (None, None) if force_refresh else cache_store.load_runs(RESULTS_ROOT)
    if runs is not None:
        return runs, meta, True
    banner = st.empty()
    banner.warning(REFRESH_NOTICE if force_refresh else FIRST_SCAN_NOTICE)
    t0 = time.time()
    if force_refresh:
        discover_runs.clear()  # bypass st.cache_data's own stale in-memory result too
    with st.spinner("Scanning RESULTS_ROOT..."):
        runs = discover_runs()
    meta = cache_store.make_meta(t0)
    cache_store.save_runs(RESULTS_ROOT, runs, meta)
    banner.empty()
    return runs, meta, False


def aggregate_runs(runs: list[dict], metric: str) -> dict[str, dict[str, list[dict]]]:
    """configs -> direction -> sorted [{size, value}] medians across runs."""
    grouped: dict[str, dict[str, dict[float, list[float]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for run in runs:
        for row in run["rows"]:
            if row["metric"] != metric:
                continue
            grouped[run["config"]][row["direction"]][row["size"]].append(row["value"])
    return {
        config: {
            direction: [{"size": size, "value": median(values)} for size, values in sorted(by_size.items())]
            for direction, by_size in by_direction.items()
        }
        for config, by_direction in grouped.items()
    }


def chart(title: str, metric: str, unit: str, y_log: bool, runs: list[dict], aggregated: dict[str, dict[str, list[dict]]], show_directions: set[str] | None = None) -> go.Figure:
    if show_directions is None:
        show_directions = {"read", "write"}
    figure = go.Figure()
    series_keys = sorted({f"{config} ({direction})" for config in aggregated for direction in aggregated[config] if direction in show_directions})
    styles = {
        key: {
            "color": PALETTE[index % len(PALETTE)],
            "dash": DASH_STYLES[index % len(DASH_STYLES)],
            "symbol": MARKER_SYMBOLS[index % len(MARKER_SYMBOLS)],
        }
        for index, key in enumerate(series_keys)
    }
    for run in runs:
        by_direction: dict[str, list[dict]] = defaultdict(list)
        for row in run["rows"]:
            if row["metric"] == metric:
                by_direction[row["direction"]].append(row)
        for direction, rows in by_direction.items():
            if direction not in show_directions:
                continue
            rows = sorted(rows, key=lambda r: r["size"])
            style = styles.get(f"{run['config']} ({direction})")
            if not style:
                continue
            figure.add_trace(go.Scatter(
                x=[row["size"] for row in rows], y=[row["value"] for row in rows],
                mode="lines", line={"color": style["color"], "width": 1, "dash": "dot"}, opacity=0.28,
                hovertemplate=f"{run['config']} {direction} | {run['id']}<br>%{{x:,.0f}} B<br>%{{y:.3f}} {unit}<extra></extra>",
                showlegend=False,
            ))
    for config, by_direction in aggregated.items():
        for direction, rows in by_direction.items():
            if direction not in show_directions:
                continue
            key = f"{config} ({direction})"
            style = styles.get(key)
            if not style:
                continue
            figure.add_trace(go.Scatter(
                x=[row["size"] for row in rows], y=[row["value"] for row in rows], mode="lines+markers",
                name=f"{key} median",
                line={"color": style["color"], "width": 3, "dash": style["dash"]},
                marker={"size": 8, "symbol": style["symbol"], "line": {"width": 1, "color": "white"}},
                hovertemplate=f"{key} median<br>%{{x:,.0f}} B<br>%{{y:.3f}} {unit}<extra></extra>",
            ))
    figure.update_layout(title=title, height=430, margin={"l": 8, "r": 8, "t": 46, "b": 92},
                         legend={"orientation": "h", "y": -0.24, "yanchor": "top"}, template="plotly_white")
    figure.update_xaxes(title="Message size (bytes)", type="log", tickformat="~s")
    figure.update_yaxes(title=f"{metric.title()} ({unit})", type="log" if y_log else "linear", rangemode="tozero")
    return figure


def metric_at(rows: list[dict], size: float) -> float | None:
    return next((row["value"] for row in rows if row["size"] == size), None)


def main() -> None:
    st.set_page_config(page_title="ze_peer PCIe Results", page_icon="Z", layout="wide")
    st.title("ze_peer P2P Bandwidth/Latency Results")
    
    force_refresh = st.sidebar.button("Refresh data", help="Re-scan RESULTS_ROOT instead of using the cached scan")
    all_runs, meta, was_cached = get_runs(force_refresh)
    
    if meta:
        age = f"{time.time() - meta['generated_at']:.0f}s ago" if was_cached else "just now"
        st.sidebar.caption(f"Scan cached {age} (took {meta['duration_seconds']}s)")
    
    skipped_results = discover_skipped_results()
    if force_refresh:
        discover_skipped_results.clear()
        skipped_results = discover_skipped_results()
    if not all_runs:
        st.info("No parseable ze_peer result files found under results/.")
        return

    if skipped_results:
        st.warning("Skipped result files with no parseable ze_peer data: " + ", ".join(skipped_results))

    configs = sorted({run["config"] for run in all_runs})
    selected_configs = st.sidebar.multiselect("Configurations", configs, default=configs)
    selected_runs = [run for run in all_runs if run["config"] in selected_configs]
    if not selected_runs:
        st.warning("Select at least one configuration.")
        return

    st.sidebar.divider()
    st.sidebar.subheader("Trace Visibility")
    show_write = st.sidebar.checkbox("Show Write traces", value=True)
    show_read = st.sidebar.checkbox("Show Read traces", value=True)
    show_directions = {direction for direction, show in [("write", show_write), ("read", show_read)] if show}
    if not show_directions:
        st.warning("Select at least one trace direction (Write or Read).")
        return

    bw_aggregated = aggregate_runs(selected_runs, "bw_gbps")
    latency_aggregated = aggregate_runs(selected_runs, "latency_us")
    st.caption(f"{len(selected_runs)} run(s) across {len(configs)} configuration(s). Thin lines are individual runs; solid lines are per-size medians.")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(chart("P2P bandwidth", "bw_gbps", "GB/s", False, selected_runs, bw_aggregated, show_directions), use_container_width=True)
    with right:
        st.plotly_chart(chart("P2P latency", "latency_us", "us", True, selected_runs, latency_aggregated, show_directions), use_container_width=True)

    summary = []
    for config in sorted(bw_aggregated):
        matching_runs = [run for run in selected_runs if run["config"] == config]
        environment = matching_runs[0]["environment"]
        write_bw = bw_aggregated[config].get("write", []) if "write" in show_directions else []
        read_bw = bw_aggregated[config].get("read", []) if "read" in show_directions else []
        write_latency = latency_aggregated.get(config, {}).get("write", []) if "write" in show_directions else []
        summary.append({
            "Configuration": config,
            "Runs": len(matching_runs),
            "8 B latency write (us)": metric_at(write_latency, 8),
            "256 MB BW write (GB/s)": metric_at(write_bw, 256 * 1024 * 1024),
            "256 MB BW read (GB/s)": metric_at(read_bw, 256 * 1024 * 1024),
            "Devices": f"{environment.get('src_device', '?')} -> {environment.get('dst_device', '?')}",
        })
    st.subheader("Median Summary")
    st.dataframe(summary, use_container_width=True, hide_index=True)

    with st.expander("Captured run metadata"):
        for run in selected_runs:
            st.markdown(f"**{run['id']}** ({run['file']})")
            st.code("\n".join(f"{key}={value}" for key, value in run["environment"].items()) or "No environment metadata found.")


if __name__ == "__main__":
    main()
