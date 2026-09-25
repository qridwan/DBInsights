"""Builds the fixed request sequence for a load run.

Every endpoint recorded in an app's ground-truth manifest is requested once
per repetition, in manifest-id order. Placeholders (`:id`, `:slug`, empty
query values) are filled from the app database via params.json, picking with
a seeded RNG, so the same seed always produces the same sequence.
"""

import json
import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from experiments.groundtruth import Manifest

PARAMS_FILE = Path(__file__).with_name("params.json")
_PATH_PARAM = re.compile(r"(?P<segment>[^/?]+)/:(?P<name>\w+)")
_EMPTY_QUERY = re.compile(r"[?&](?P<name>\w+)=(?=&|$)")


@dataclass(frozen=True)
class PlannedRequest:
    seq: int
    entry_id: str
    method: str
    #: Concrete path with query string, e.g. /api/orders/0000…/invoice
    path: str
    #: Next.js route pattern the collector reports, e.g. /api/orders/[id]/invoice
    route: str


def route_pattern(endpoint: str) -> str:
    """'GET /api/orders/:id/invoice?x=1' -> '/api/orders/[id]/invoice'."""
    path = endpoint.split(" ", 1)[-1].split("?", 1)[0]
    return re.sub(r":(\w+)", r"[\1]", path)


def placeholders(endpoint: str) -> list[str]:
    """Parameter-source keys an endpoint needs, e.g. ['orders/:id']."""
    path = endpoint.split(" ", 1)[-1]
    keys = [f"{m['segment']}/:{m['name']}" for m in _PATH_PARAM.finditer(path.split("?", 1)[0])]
    if "?" in path:
        keys += [f"?{m['name']}=" for m in _EMPTY_QUERY.finditer("?" + path.split("?", 1)[1])]
    return keys


def load_param_sources(app: str) -> dict[str, str]:
    return json.loads(PARAMS_FILE.read_text(encoding="utf-8"))[app]


def build_sequence(
    manifest: Manifest,
    candidates: dict[str, list[str]],
    *,
    seed: int,
    repetitions: int,
) -> list[PlannedRequest]:
    """The deterministic request sequence. `candidates` maps each parameter key to its values."""
    entries = sorted((e for e in manifest.entries if e.endpoint), key=lambda e: e.id)
    rng = random.Random(seed)
    sequence: list[PlannedRequest] = []
    for _ in range(repetitions):
        for entry in entries:
            method, template = entry.endpoint.split(" ", 1)
            path = template
            for key in placeholders(entry.endpoint):
                values = candidates.get(key)
                if not values:
                    raise ValueError(
                        f"{entry.id}: no values for {key!r}; add a source to params.json"
                    )
                value = quote(rng.choice(values), safe="")
                if key.startswith("?"):
                    name = key[1:-1]
                    path = re.sub(rf"([?&]{name}=)(?=&|$)", rf"\g<1>{value}", path)
                else:
                    segment, name = key.split("/:")
                    path = path.replace(f"{segment}/:{name}", f"{segment}/{value}", 1)
            sequence.append(
                PlannedRequest(
                    seq=len(sequence),
                    entry_id=entry.id,
                    method=method,
                    path=path,
                    route=route_pattern(entry.endpoint),
                )
            )
    return sequence


def resolve_candidates(
    app: str, fetch: Callable[[str], list[str]], manifest: Manifest
) -> dict[str, list[str]]:
    """Runs the parameter-source query for every placeholder the manifest uses."""
    sources = load_param_sources(app)
    needed = {key for e in manifest.entries if e.endpoint for key in placeholders(e.endpoint)}
    missing = needed - sources.keys()
    if missing:
        raise ValueError(f"params.json has no source for {sorted(missing)} in app {app!r}")
    return {key: fetch(sources[key]) for key in sorted(needed)}
