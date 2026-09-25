import math

import pytest

from experiments.load.analysis import overhead, repeatability
from experiments.load.resources import parse_cpu, parse_memory


def counts(**routes: int):
    return [{"route": route, "operations": n, "statements": n} for route, n in routes.items()]


def test_identical_runs_have_zero_spread_and_pass():
    summary = repeatability([counts(a=100, b=20)] * 5)
    assert summary["max_relative_deviation"] == {"operations": 0.0, "statements": 0.0}
    assert summary["passes"] is True


def test_spread_is_the_largest_deviation_from_the_mean():
    summary = repeatability([counts(a=100), counts(a=100), counts(a=106)])
    assert summary["max_relative_deviation"]["statements"] == pytest.approx(4 / 102)
    assert summary["passes"] is True


def test_five_percent_or_more_fails():
    assert repeatability([counts(a=100), counts(a=112)])["passes"] is False


def test_one_route_varying_fails_even_if_totals_barely_move():
    summary = repeatability([counts(a=1000, b=10), counts(a=1000, b=13)])
    assert summary["max_relative_deviation"]["statements"] < 0.05
    assert summary["passes"] is False


def test_a_single_run_cannot_demonstrate_repeatability():
    assert repeatability([counts(a=1)])["passes"] is False


def request(entry, latency, enabled, *, warmup=False, status=200):
    return {
        "entry_id": entry,
        "latency_ms": latency,
        "collector_enabled": enabled,
        "warmup": warmup,
        "status": status,
    }


def test_overhead_compares_medians_and_excludes_warmup_and_failures():
    rows = [
        request("a", 10, True),
        request("a", 12, True),
        request("a", 11, True),
        request("a", 9, False),
        request("a", 10, False),
        request("a", 8, False),
        request("a", 999, True, warmup=True),
        request("a", 999, False, status=500),
    ]
    samples = [
        {
            "service": "app",
            "cpu_percent": 20.0,
            "memory_bytes": 200 * 1024**2,
            "collector_enabled": True,
            "warmup": False,
        },
        {
            "service": "app",
            "cpu_percent": 10.0,
            "memory_bytes": 180 * 1024**2,
            "collector_enabled": False,
            "warmup": False,
        },
    ]
    result = overhead(rows, samples)
    assert result["latency"]["on"]["median_ms"] == 11
    assert result["latency"]["off"]["median_ms"] == 9
    assert result["median_overhead_ms"] == 2
    assert result["median_overhead_ratio"] == pytest.approx(2 / 9)
    assert result["per_entry"]["a"]["median_delta_ms"] == 2
    assert result["resources"]["app"]["on"]["memory_mib_mean"] == 200
    assert result["resources"]["app"]["off"]["cpu_percent_mean"] == 10


def counter(service, enabled, cpu_usec, requests, *, warmup=False, mem=100):
    return {
        "service": service,
        "collector_enabled": enabled,
        "warmup": warmup,
        "cpu_usec": cpu_usec,
        "requests": requests,
        "memory_end_bytes": mem * 1024**2,
        "memory_peak_bytes": (mem + 50) * 1024**2,
    }


def test_cpu_cost_per_request_comes_from_counter_deltas():
    rows = [
        counter("app", True, 3_000_000, 100),
        counter("app", True, 3_200_000, 100),
        counter("app", False, 2_000_000, 100),
        counter("app", False, 2_000_000, 100),
        counter("app", True, 99_000_000, 100, warmup=True),
        counter("collector", True, 5_000_000, 100),
        counter("collector", False, 0, 100),
    ]
    cost = overhead([], [], rows)["cost"]
    assert cost["app"]["on"]["cpu_ms_per_request_mean"] == pytest.approx(31)
    assert cost["app"]["off"]["cpu_ms_per_request_mean"] == pytest.approx(20)
    assert cost["app"]["on"]["runs"] == 2, "warm-up excluded"
    assert cost["collector"]["off"]["cpu_ms_per_request_mean"] == 0
    assert cost["app"]["on"]["memory_mib_peak_max"] == 150


def test_overhead_without_both_conditions_is_undefined_not_zero():
    result = overhead([request("a", 10, True)], [])
    assert math.isnan(result["median_overhead_ms"])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("123.4MiB / 7.66GiB", int(123.4 * 1024**2)),
        ("1.5GiB / 8GiB", int(1.5 * 1024**3)),
        ("512KiB / 1GiB", 512 * 1024),
    ],
)
def test_parse_docker_memory(raw, expected):
    assert parse_memory(raw) == expected


def test_parse_docker_cpu():
    assert parse_cpu("12.34%") == 12.34
    assert parse_cpu("0.00%") == 0.0
