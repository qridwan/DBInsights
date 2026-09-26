"""Accounts, one-time codes and sessions in Postgres (schema `dashboard`)."""

import secrets
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS dashboard;

CREATE TABLE IF NOT EXISTS dashboard.app_user (
  user_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email             text NOT NULL UNIQUE,
  name              text NOT NULL DEFAULT '',
  password_hash     text NOT NULL,
  role              text NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
  email_verified_at timestamptz,
  disabled          boolean NOT NULL DEFAULT false,
  created_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at        timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS dashboard.auth_otp (
  email      text NOT NULL,
  purpose    text NOT NULL CHECK (purpose IN ('register', 'reset')),
  code_hash  text NOT NULL,
  expires_at timestamptz NOT NULL,
  attempts   integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (email, purpose)
);

CREATE TABLE IF NOT EXISTS dashboard.auth_session (
  token_hash   text PRIMARY KEY,
  user_id      uuid NOT NULL REFERENCES dashboard.app_user (user_id) ON DELETE CASCADE,
  created_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
  last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at   timestamptz NOT NULL,
  user_agent   text,
  ip           text
);
CREATE INDEX IF NOT EXISTS auth_session_user_idx ON dashboard.auth_session (user_id);

-- Rate-limit ledger: sends of codes and login attempts, keyed by email or address.
CREATE TABLE IF NOT EXISTS dashboard.auth_event (
  event_id bigserial PRIMARY KEY,
  kind     text NOT NULL,
  key      text NOT NULL,
  ok       boolean NOT NULL DEFAULT true,
  at       timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS auth_event_lookup_idx ON dashboard.auth_event (kind, key, at);

CREATE TABLE IF NOT EXISTS dashboard.app_secret (name text PRIMARY KEY, value text NOT NULL);
"""


class AuthStore:
    def __init__(self, database_url: str) -> None:
        self.conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
        self.conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def secret(self) -> bytes:
        """The key one-time codes are hashed with; created once and kept in the database."""
        row = self.conn.execute(
            "SELECT value FROM dashboard.app_secret WHERE name = 'otp'"
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO dashboard.app_secret (name, value) VALUES ('otp', %s) ON CONFLICT DO NOTHING",
                (secrets.token_hex(32),),
            )
            row = self.conn.execute(
                "SELECT value FROM dashboard.app_secret WHERE name = 'otp'"
            ).fetchone()
        return bytes.fromhex(row["value"])

    # ---- users -----------------------------------------------------------

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM dashboard.app_user WHERE email = %s", (email,)
        ).fetchone()

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM dashboard.app_user WHERE user_id = %s", (user_id,)
        ).fetchone()

    def create_user(self, email: str, password_hash: str, name: str) -> dict[str, Any]:
        return self.conn.execute(
            "INSERT INTO dashboard.app_user (email, password_hash, name) VALUES (%s, %s, %s) RETURNING *",
            (email, password_hash, name),
        ).fetchone()

    def update_pending(self, user_id: str, password_hash: str, name: str) -> None:
        self.conn.execute(
            "UPDATE dashboard.app_user SET password_hash = %s, name = %s, updated_at = clock_timestamp()"
            " WHERE user_id = %s AND email_verified_at IS NULL",
            (password_hash, name, user_id),
        )

    def count_verified(self) -> int:
        row = self.conn.execute(
            "SELECT count(*) AS n FROM dashboard.app_user WHERE email_verified_at IS NOT NULL"
        ).fetchone()
        return int(row["n"])

    def mark_verified(self, user_id: str, role: str) -> dict[str, Any]:
        return self.conn.execute(
            "UPDATE dashboard.app_user SET email_verified_at = COALESCE(email_verified_at, clock_timestamp()),"
            " role = %s, updated_at = clock_timestamp() WHERE user_id = %s RETURNING *",
            (role, user_id),
        ).fetchone()

    def set_password(self, user_id: str, password_hash: str) -> None:
        self.conn.execute(
            "UPDATE dashboard.app_user SET password_hash = %s, updated_at = clock_timestamp() WHERE user_id = %s",
            (password_hash, user_id),
        )

    def set_name(self, user_id: str, name: str) -> None:
        self.conn.execute(
            "UPDATE dashboard.app_user SET name = %s, updated_at = clock_timestamp() WHERE user_id = %s",
            (name, user_id),
        )

    # ---- one-time codes --------------------------------------------------

    def put_otp(self, email: str, purpose: str, code_hash: str, expires_at: datetime) -> None:
        self.conn.execute(
            """INSERT INTO dashboard.auth_otp (email, purpose, code_hash, expires_at, attempts)
               VALUES (%s, %s, %s, %s, 0)
               ON CONFLICT (email, purpose) DO UPDATE SET code_hash = EXCLUDED.code_hash,
                 expires_at = EXCLUDED.expires_at, attempts = 0, created_at = clock_timestamp()""",
            (email, purpose, code_hash, expires_at),
        )

    def get_otp(self, email: str, purpose: str) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM dashboard.auth_otp WHERE email = %s AND purpose = %s", (email, purpose)
        ).fetchone()

    def bump_otp_attempts(self, email: str, purpose: str) -> int:
        row = self.conn.execute(
            "UPDATE dashboard.auth_otp SET attempts = attempts + 1 WHERE email = %s AND purpose = %s RETURNING attempts",
            (email, purpose),
        ).fetchone()
        return int(row["attempts"]) if row else 0

    def delete_otp(self, email: str, purpose: str) -> None:
        self.conn.execute(
            "DELETE FROM dashboard.auth_otp WHERE email = %s AND purpose = %s", (email, purpose)
        )

    # ---- sessions --------------------------------------------------------

    def create_session(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip: str | None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO dashboard.auth_session (token_hash, user_id, expires_at, user_agent, ip) VALUES (%s, %s, %s, %s, %s)",
            (token_hash, user_id, expires_at, (user_agent or "")[:300], ip),
        )

    def get_session(self, token_hash: str) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT s.*, u.email, u.name, u.role, u.disabled, u.email_verified_at, u.created_at AS user_created_at"
            " FROM dashboard.auth_session s JOIN dashboard.app_user u USING (user_id) WHERE s.token_hash = %s",
            (token_hash,),
        ).fetchone()

    def touch_session(self, token_hash: str) -> None:
        self.conn.execute(
            "UPDATE dashboard.auth_session SET last_seen_at = clock_timestamp() WHERE token_hash = %s",
            (token_hash,),
        )

    def delete_session(self, token_hash: str) -> None:
        self.conn.execute("DELETE FROM dashboard.auth_session WHERE token_hash = %s", (token_hash,))

    def delete_user_sessions(self, user_id: str, keep: str | None = None) -> int:
        return self.conn.execute(
            "DELETE FROM dashboard.auth_session WHERE user_id = %s AND (%s::text IS NULL OR token_hash <> %s)",
            (user_id, keep, keep),
        ).rowcount

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT token_hash, created_at, last_seen_at, expires_at, user_agent, ip FROM dashboard.auth_session"
            " WHERE user_id = %s AND expires_at > clock_timestamp() ORDER BY last_seen_at DESC",
            (user_id,),
        ).fetchall()

    # ---- rate-limit ledger -----------------------------------------------

    def record_event(self, kind: str, key: str, ok: bool = True) -> None:
        self.conn.execute(
            "INSERT INTO dashboard.auth_event (kind, key, ok) VALUES (%s, %s, %s)", (kind, key, ok)
        )

    def events_since(
        self, kind: str, key: str, since: datetime, only_failures: bool = False
    ) -> list[datetime]:
        rows = self.conn.execute(
            "SELECT at FROM dashboard.auth_event WHERE kind = %s AND key = %s AND at >= %s"
            " AND (NOT %s OR NOT ok) ORDER BY at",
            (kind, key, since, only_failures),
        ).fetchall()
        return [r["at"] for r in rows]

    def clear_events(self, kind: str, key: str) -> None:
        self.conn.execute(
            "DELETE FROM dashboard.auth_event WHERE kind = %s AND key = %s", (kind, key)
        )

    def purge_old(self, before: datetime) -> None:
        self.conn.execute("DELETE FROM dashboard.auth_event WHERE at < %s", (before,))
        self.conn.execute("DELETE FROM dashboard.auth_otp WHERE expires_at < %s", (before,))
        self.conn.execute("DELETE FROM dashboard.auth_session WHERE expires_at < %s", (before,))
