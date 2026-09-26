"""Explanation cache, keyed by (ruleId, hash(evidence)).

Identical findings in different places share one model call. A cached entry is used only if it
was produced under the same prompt version and model; anything else counts as a miss, so
changing either invalidates the cache without deleting anything.
"""

import hashlib
import json
from dataclasses import asdict
from typing import Protocol

import psycopg
from psycopg.rows import dict_row

from .contract import Explanation
from .projection import FindingView


def evidence_hash(view: FindingView) -> str:
    canonical = json.dumps(
        [asdict(e) for e in view.evidence], sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class ExplanationCache(Protocol):
    def get(self, rule_id: str, digest: str, version: str) -> Explanation | None: ...

    def put(self, rule_id: str, digest: str, version: str, explanation: Explanation) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], tuple[str, Explanation]] = {}

    def get(self, rule_id: str, digest: str, version: str) -> Explanation | None:
        held = self._items.get((rule_id, digest))
        return held[1] if held and held[0] == version else None

    def put(self, rule_id: str, digest: str, version: str, explanation: Explanation) -> None:
        self._items[(rule_id, digest)] = (version, explanation)


SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS explain;
CREATE TABLE IF NOT EXISTS explain.cache (
  rule_id        text NOT NULL,
  evidence_hash  text NOT NULL,
  version        text NOT NULL,
  explanation    text NOT NULL,
  recommendation text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (rule_id, evidence_hash)
);
"""


class PostgresCache:
    def __init__(self, database_url: str) -> None:
        self.conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
        self.conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def get(self, rule_id: str, digest: str, version: str) -> Explanation | None:
        row = self.conn.execute(
            "SELECT explanation, recommendation FROM explain.cache "
            "WHERE rule_id = %s AND evidence_hash = %s AND version = %s",
            (rule_id, digest, version),
        ).fetchone()
        return Explanation(**row) if row else None

    def put(self, rule_id: str, digest: str, version: str, explanation: Explanation) -> None:
        self.conn.execute(
            """INSERT INTO explain.cache
                 (rule_id, evidence_hash, version, explanation, recommendation)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (rule_id, evidence_hash) DO UPDATE SET version = EXCLUDED.version,
                 explanation = EXCLUDED.explanation, recommendation = EXCLUDED.recommendation,
                 created_at = clock_timestamp()""",
            (rule_id, digest, version, explanation.explanation, explanation.recommendation),
        )
