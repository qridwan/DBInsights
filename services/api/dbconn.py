"""A database connection that survives the server dropping it."""

from typing import Any

import psycopg
from psycopg.rows import dict_row


class ReconnectingConnection:
    """One autocommit connection that is reopened when the server has dropped it.

    A long-running API outlives database restarts and idle timeouts; every statement here is
    independent, so retrying once on a fresh connection is safe.
    """

    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._conn = self._open()

    def _open(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self._url, autocommit=True, row_factory=dict_row)

    def live(self) -> psycopg.Connection[dict[str, Any]]:
        if self._conn.closed or self._conn.broken:
            self._conn = self._open()
        return self._conn

    def execute(self, query: Any, params: Any = None) -> psycopg.Cursor[dict[str, Any]]:
        if self._conn.closed or self._conn.broken:
            self._conn = self._open()
        try:
            return self._conn.execute(query, params)
        except psycopg.OperationalError:
            try:
                self._conn.close()
            except psycopg.Error:
                pass
            self._conn = self._open()
            return self._conn.execute(query, params)

    def close(self) -> None:
        self._conn.close()
