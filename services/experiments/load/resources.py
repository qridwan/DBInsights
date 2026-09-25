"""Container CPU and memory for the overhead measurement.

Two sources, both stored raw:
- cgroup v2 counters read at the start and end of a run (`read_counters`):
  exact CPU time consumed and memory, independent of sampling. These are the
  primary RQ5 measurements.
- `docker stats` samples during a run (`ResourceSampler`): a coarse time series,
  one sample per container every ~1-2 s.
"""

import json
import re
import subprocess
import threading
from datetime import UTC, datetime
from typing import Any

_UNITS = {
    "b": 1,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
}


def parse_memory(value: str) -> int:
    """'123.4MiB / 7.66GiB' -> bytes used."""
    match = re.match(r"\s*([\d.]+)\s*([A-Za-z]+)", value)
    if not match:
        raise ValueError(f"unrecognised memory value {value!r}")
    return int(float(match.group(1)) * _UNITS[match.group(2).lower()])


def parse_cpu(value: str) -> float:
    return float(value.strip().rstrip("%") or 0)


def container_ids(repo_root: str, services: list[str]) -> dict[str, str]:
    ids = {}
    for service in services:
        out = subprocess.run(
            ["docker", "compose", "ps", "-q", service],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if out:
            ids[out.splitlines()[0]] = service
    return ids


class ResourceSampler:
    """Background thread; each `docker stats --no-stream` call takes one sample per container."""

    def __init__(self, repo_root: str, services: list[str]) -> None:
        self._ids = container_ids(repo_root, services)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self.samples: list[dict[str, Any]] = []

    def __enter__(self) -> "ResourceSampler":
        if self._ids:
            self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            completed = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", *self._ids],
                capture_output=True,
                text=True,
                check=False,
            )
            sampled_at = datetime.now(UTC)
            for line in completed.stdout.splitlines():
                stat = json.loads(line)
                service = next(
                    (s for cid, s in self._ids.items() if stat.get("ID", "").startswith(cid[:12])),
                    None,
                )
                if service:
                    self.samples.append(
                        {
                            "sampled_at": sampled_at,
                            "service": service,
                            "cpu_percent": parse_cpu(stat["CPUPerc"]),
                            "memory_bytes": parse_memory(stat["MemUsage"]),
                        }
                    )


_COUNTERS_SCRIPT = (
    "awk '/^usage_usec/ {print \"cpu_usage_usec\", $2}' /sys/fs/cgroup/cpu.stat; "
    "echo memory_current_bytes $(cat /sys/fs/cgroup/memory.current); "
    "echo memory_peak_bytes $(cat /sys/fs/cgroup/memory.peak 2>/dev/null || echo 0)"
)


def read_counters(repo_root: str, services: list[str]) -> dict[str, dict[str, int]]:
    """cgroup v2 CPU time (µs, cumulative) and memory (bytes) for each compose service."""
    counters: dict[str, dict[str, int]] = {}
    for service in services:
        completed = subprocess.run(
            ["docker", "compose", "exec", "-T", service, "sh", "-c", _COUNTERS_SCRIPT],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        values = dict(line.split() for line in completed.stdout.splitlines() if line.strip())
        if values:
            counters[service] = {key: int(value) for key, value in values.items()}
    return counters
