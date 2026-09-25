"""Executes a request sequence against an app, one request at a time."""

import http.client
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from .sequence import PlannedRequest


def execute(
    sequence: list[PlannedRequest], base_url: str, *, timeout: float = 120.0
) -> list[dict[str, Any]]:
    """Sequential and keep-alive, so latency differences come from the app, not the harness."""
    target = urlsplit(base_url)
    conn = http.client.HTTPConnection(
        target.hostname or "localhost", target.port or 80, timeout=timeout
    )
    results = []
    try:
        for request in sequence:
            started_at = datetime.now(UTC)
            start = time.perf_counter()
            status, size = 0, 0
            for attempt in range(2):
                try:
                    conn.request(
                        request.method, request.path, headers={"accept": "application/json"}
                    )
                    response = conn.getresponse()
                    size = len(response.read())
                    status = response.status
                    break
                except (http.client.HTTPException, OSError):
                    conn.close()
                    if attempt == 1:
                        status = 0
            results.append(
                {
                    "seq": request.seq,
                    "entry_id": request.entry_id,
                    "method": request.method,
                    "path": request.path,
                    "route": request.route,
                    "status": status,
                    "latency_ms": (time.perf_counter() - start) * 1000,
                    "response_bytes": size,
                    "started_at": started_at,
                }
            )
    finally:
        conn.close()
    return results


def wait_until_ready(base_url: str, *, timeout: float = 180.0) -> None:
    target = urlsplit(base_url)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            conn = http.client.HTTPConnection(
                target.hostname or "localhost", target.port or 80, timeout=5
            )
            conn.request("GET", "/")
            if conn.getresponse().status == 200:
                return
        except (http.client.HTTPException, OSError):
            pass
        time.sleep(1)
    raise TimeoutError(f"{base_url} did not become ready within {timeout:.0f}s")
