"""Apply an app's data-quality problems to its database, after the clean seed.

    python -m experiments.groundtruth.inject ecommerce [--dry-run]

Runs `<app>.sql` through psql in the docker compose `postgres` service. The
SQL is idempotent, so running it twice leaves the database unchanged.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO_ROOT = HERE.parents[3]
APPS = sorted(path.stem for path in HERE.glob("*.sql"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m experiments.groundtruth.inject", description=__doc__
    )
    parser.add_argument("app", choices=APPS)
    parser.add_argument(
        "--dry-run", action="store_true", help="print the SQL instead of running it"
    )
    args = parser.parse_args(argv)

    sql = (HERE / f"{args.app}.sql").read_text(encoding="utf-8")
    if args.dry_run:
        sys.stdout.write(sql)
        return 0

    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        os.environ.get("POSTGRES_USER", "dbinsight"),
        "-d",
        args.app,
    ]
    return subprocess.run(command, input=sql, text=True, cwd=REPO_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
