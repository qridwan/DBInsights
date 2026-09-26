"""Calls the TypeScript analyzer (packages/core) as a subprocess.

The Python services never reimplement static analysis: they send one JSON
request to `dist/cli.js` on stdin and read one JSON response from stdout.
Build the core first (`pnpm --filter @dbinsight/core build`).
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLI = REPO_ROOT / "packages" / "core" / "dist" / "cli.js"


class CoreError(RuntimeError):
    """The TypeScript core rejected the request or could not be run."""


def core_cli_path() -> Path:
    return Path(os.environ.get("DBINSIGHT_CORE_CLI", DEFAULT_CLI))


def call_core(request: dict[str, Any], timeout: float | None = None) -> Any:
    cli = core_cli_path()
    if not cli.exists():
        raise CoreError(f"{cli} not found; build it with `pnpm --filter @dbinsight/core build`")
    try:
        completed = subprocess.run(
            ["node", str(cli)],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise CoreError(f"core did not finish within {timeout}s") from error
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise CoreError(
            f"core returned no JSON (exit {completed.returncode}): {completed.stderr.strip()}"
        ) from error
    if not response.get("ok"):
        raise CoreError(response.get("error", "unknown core error"))
    return response["result"]


def parse_schema(schema_path: str | Path) -> Any:
    return call_core({"command": "parseSchema", "schemaPath": str(Path(schema_path).resolve())})


def analyze(
    source_dir: str | Path, schema_path: str | Path | None = None, timeout: float | None = None
) -> Any:
    """Static analysis. Without a schema path, rules that need the declared schema are silent."""
    request: dict[str, Any] = {"command": "analyze", "sourceDir": str(Path(source_dir).resolve())}
    if schema_path is not None:
        request["schemaPath"] = str(Path(schema_path).resolve())
    return call_core(request, timeout)
