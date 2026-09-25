"""Score a findings file against a manifest.

python -m experiments.groundtruth --manifest manifests/ecommerce.json --findings findings.json
"""

import argparse
import json
import sys
from pathlib import Path

from .finding import parse_findings
from .manifest import load_manifest
from .scorer import score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m experiments.groundtruth", description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--findings", type=Path, required=True, help="JSON array of Finding (schemaVersion 1)"
    )
    parser.add_argument("--out", type=Path, help="write the report here instead of stdout")
    args = parser.parse_args(argv)

    findings = parse_findings(json.loads(args.findings.read_text(encoding="utf-8")))
    report = score(findings, load_manifest(args.manifest)).model_dump_json(by_alias=True, indent=2)
    if args.out:
        args.out.write_text(report + "\n", encoding="utf-8")
    else:
        sys.stdout.write(report + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
