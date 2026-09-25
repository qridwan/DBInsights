"""Analysis over raw harness data. Pure functions; nothing here writes."""

import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

REPEATABILITY_LIMIT = 0.05  # M3.3: query counts across runs must vary by under 5%


def _relative_spread(values: Sequence[float]) -> float:
    """Largest deviation from the mean, as a fraction of the mean."""
    mean = statistics.fmean(values)
    return 0.0 if mean == 0 else max(abs(v - mean) for v in values) / mean


def repeatability(per_run: Sequence[Sequence[dict[str, Any]]]) -> dict[str, Any]:
    """`per_run`: for each run, the collector's per-route counts (route, operations, statements)."""
    totals = [
        {
            "operations": sum(r["operations"] for r in rows),
            "statements": sum(r["statements"] for r in rows),
        }
        for rows in per_run
    ]
    routes = sorted({r["route"] for rows in per_run for r in rows})
    by_route = {}
    for route in routes:
        counts = [
            next((r["statements"] for r in rows if r["route"] == route), 0) for rows in per_run
        ]
        by_route[route] = {"statements": counts, "max_relative_deviation": _relative_spread(counts)}

    spread = {
        key: _relative_spread([t[key] for t in totals]) for key in ("operations", "statements")
    }
    worst_route = max((v["max_relative_deviation"] for v in by_route.values()), default=0.0)
    return {
        "runs": len(per_run),
        "totals": totals,
        "max_relative_deviation": spread,
        "worst_route_relative_deviation": worst_route,
        "limit": REPEATABILITY_LIMIT,
        "passes": len(per_run) >= 2 and max(*spread.values(), worst_route) < REPEATABILITY_LIMIT,
        "by_route": by_route,
    }


def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    index = (len(ordered) - 1) * q
    low, high = int(index), min(int(index) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def _latency_stats(values: Sequence[float]) -> dict[str, float]:
    return {
        "n": len(values),
        "median_ms": _percentile(values, 0.5),
        "p95_ms": _percentile(values, 0.95),
        "mean_ms": statistics.fmean(values) if values else float("nan"),
    }


def _cost(counters: Iterable[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Per service and condition: CPU time per request from cgroup counter deltas, and memory."""
    usable = [c for c in counters if not c["warmup"] and c["requests"]]
    cost: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for service in sorted({c["service"] for c in usable}):
        for state, enabled in (("on", True), ("off", False)):
            rows = [
                c for c in usable if c["service"] == service and c["collector_enabled"] is enabled
            ]
            if not rows:
                continue
            per_request = [c["cpu_usec"] / c["requests"] / 1000 for c in rows]
            cost[service][state] = {
                "runs": len(rows),
                "cpu_ms_per_request_mean": statistics.fmean(per_request),
                "cpu_ms_per_request_runs": per_request,
                "memory_mib_end_mean": statistics.fmean(c["memory_end_bytes"] for c in rows)
                / 1024**2,
                "memory_mib_peak_max": max(c["memory_peak_bytes"] for c in rows) / 1024**2,
            }
    return dict(cost)


def overhead(
    requests: Iterable[dict[str, Any]],
    samples: Iterable[dict[str, Any]],
    counters: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Collector on vs off. Warm-up runs and failed requests are excluded.

    `cost` (cgroup counter deltas) is the primary CPU/memory measurement;
    `resources` (docker stats samples) is a coarse time series kept alongside.
    """
    measured = [r for r in requests if not r["warmup"] and r["status"] == 200]
    latency = {
        state: _latency_stats(
            [r["latency_ms"] for r in measured if r["collector_enabled"] is enabled]
        )
        for state, enabled in (("on", True), ("off", False))
    }

    per_entry: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"on": [], "off": []})
    for r in measured:
        per_entry[r["entry_id"]]["on" if r["collector_enabled"] else "off"].append(r["latency_ms"])
    entries = {
        entry: {
            "median_on_ms": _percentile(v["on"], 0.5),
            "median_off_ms": _percentile(v["off"], 0.5),
            "median_delta_ms": _percentile(v["on"], 0.5) - _percentile(v["off"], 0.5),
        }
        for entry, v in sorted(per_entry.items())
        if v["on"] and v["off"]
    }

    resources: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    usable = [s for s in samples if not s["warmup"]]
    for service in sorted({s["service"] for s in usable}):
        for state, enabled in (("on", True), ("off", False)):
            rows = [
                s for s in usable if s["service"] == service and s["collector_enabled"] is enabled
            ]
            if rows:
                resources[service][state] = {
                    "samples": len(rows),
                    "cpu_percent_mean": statistics.fmean(s["cpu_percent"] for s in rows),
                    "memory_mib_mean": statistics.fmean(s["memory_bytes"] for s in rows) / 1024**2,
                    "memory_mib_max": max(s["memory_bytes"] for s in rows) / 1024**2,
                }

    on, off = latency["on"], latency["off"]
    return {
        "latency": latency,
        "median_overhead_ms": on["median_ms"] - off["median_ms"],
        "median_overhead_ratio": (on["median_ms"] / off["median_ms"] - 1)
        if off["median_ms"]
        else float("nan"),
        "p95_overhead_ms": on["p95_ms"] - off["p95_ms"],
        "per_entry": entries,
        "cost": _cost(counters),
        "resources": dict(resources),
    }
