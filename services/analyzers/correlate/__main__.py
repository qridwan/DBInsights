"""Correlate the findings of several evidence layers into single scored findings.

    python -m analyzers.correlate --findings static.json --findings runtime.json \\
        --findings divergence.json --findings data.json \\
        --declared-schema ../apps/shop/prisma/schema.prisma --database-url postgresql://.../shop

Each --findings file is a JSON array of Finding, as produced by that layer's own command.
The declared schema and the actual database are optional; a layer that is absent has no
opinion. Prints Finding[] (the scorer's input), or with --report every decision: the
hypotheses considered at each site, their scores, and the evidence for and against each.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..finding import parse_findings
from ..schema.actual import connect, read_actual_schema
from ..schema.declared import load_declared_schema
from .engine import CorrelationResult, correlate
from .facts import SchemaFacts


def _report(result: CorrelationResult) -> dict[str, Any]:
    return {
        "input_consumed": sum(len(d.consumed) for d in result.decisions),
        "findings": len(result.findings),
        "decisions": [
            {
                "site": d.site,
                "type_changed_from": d.type_changed_from,
                "consumed": list(d.consumed),
                "hypotheses": [
                    {
                        "rule_id": h.rule_id,
                        "emitted": h.emitted,
                        "posterior": h.posterior,
                        "confidence": h.confidence,
                        "log_odds": h.logit,
                        "evidence": [
                            {
                                "layer": c.layer,
                                "role": c.role,
                                "weight": c.weight,
                                "description": c.evidence.description,
                            }
                            for c in h.contributions
                        ],
                    }
                    for h in d.hypotheses
                ],
            }
            for d in result.decisions
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m analyzers.correlate",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--findings", type=Path, action="append", required=True, metavar="FILE")
    parser.add_argument(
        "--declared-schema", type=Path, help="schema.prisma (via the TypeScript core)"
    )
    parser.add_argument(
        "--database-url", help="the app database: supplies the actual schema (read-only)"
    )
    parser.add_argument("--db-schema", default="public")
    parser.add_argument(
        "--report", action="store_true", help="print the decisions instead of findings"
    )
    args = parser.parse_args(argv)

    findings = [
        f
        for path in args.findings
        for f in parse_findings(json.loads(path.read_text(encoding="utf-8")))
    ]
    declared = load_declared_schema(args.declared_schema) if args.declared_schema else None
    actual = None
    if args.database_url:
        with connect(args.database_url) as conn:
            actual = read_actual_schema(conn, args.db_schema)

    result = correlate(findings, facts=SchemaFacts(declared=declared, actual=actual))
    if args.report:
        sys.stdout.write(json.dumps(_report(result), indent=2) + "\n")
    else:
        payload = [
            f.model_dump(mode="json", by_alias=True, exclude_none=True) for f in result.findings
        ]
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
