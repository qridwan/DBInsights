"""Compare schema.prisma with a live PostgreSQL database.

    python -m analyzers.schema --schema ../apps/ecommerce/prisma/schema.prisma \\
        --database-url postgresql://dbinsight:dbinsight@localhost:5432/ecommerce \\
        [--format report|findings|actual]

`report` prints every divergence category; `findings` prints Finding[] (the
scorer's input); `actual` prints the raw ActualSchema.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from .actual import connect, read_actual_schema
from .declared import load_declared_schema
from .divergence import compare, to_findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m analyzers.schema", description=__doc__)
    parser.add_argument("--schema", type=Path, required=True, help="path to schema.prisma")
    parser.add_argument(
        "--database-url", default=os.environ.get("DATABASE_URL"), help="defaults to $DATABASE_URL"
    )
    parser.add_argument(
        "--db-schema", default="public", help="PostgreSQL schema to read (default: public)"
    )
    parser.add_argument("--format", choices=["report", "findings", "actual"], default="report")
    parser.add_argument(
        "--schema-file",
        help="how findings refer to the schema file (default: prisma/schema.prisma)",
    )
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    declared = load_declared_schema(args.schema)
    with connect(args.database_url) as conn:
        actual = read_actual_schema(conn, args.db_schema)

    if args.format == "actual":
        output = actual.model_dump(mode="json")
    elif args.format == "report":
        output = compare(declared, actual).model_dump(mode="json")
    else:
        schema_file = args.schema_file or "prisma/schema.prisma"
        output = [
            f.model_dump(mode="json", by_alias=True, exclude_none=True)
            for f in to_findings(compare(declared, actual), schema_file)
        ]
    sys.stdout.write(json.dumps(output, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
