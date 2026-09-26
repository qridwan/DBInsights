"""The Postgres side of accounts: the SQL the in-memory fake cannot exercise."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from api.dashboard.auth.service import AuthService, hash_token
from api.dashboard.auth.store import AuthStore
from tests.api.auth_fakes import FAST, Mail

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DBINSIGHT_TEST_DATABASE_URL")
        or os.environ.get("DBINSIGHT_RESULTS_DATABASE_URL")
    ),
    reason="no database configured",
)


@pytest.fixture
def store():
    s = AuthStore(
        os.environ.get("DBINSIGHT_TEST_DATABASE_URL")
        or os.environ["DBINSIGHT_RESULTS_DATABASE_URL"]
    )
    yield s
    s.conn.execute("DELETE FROM dashboard.app_user WHERE email LIKE %s", ("%@auth-test.invalid",))
    s.conn.execute("DELETE FROM dashboard.auth_otp WHERE email LIKE %s", ("%@auth-test.invalid",))
    s.conn.execute("DELETE FROM dashboard.auth_event WHERE key LIKE %s", ("%auth-test%",))
    s.close()


def email():
    return f"{uuid.uuid4().hex[:10]}@auth-test.invalid"


def test_the_code_secret_is_created_once_and_then_stable(store):
    first = store.secret()
    assert len(first) == 32 and store.secret() == first


def test_users_are_unique_by_email_and_can_be_verified(store):
    address = email()
    user = store.create_user(address, "hash", "Ada")
    assert user["email_verified_at"] is None and user["role"] == "user"
    with pytest.raises(Exception):  # noqa: B017 - a unique violation
        store.create_user(address, "other", "Dup")
    verified = store.mark_verified(str(user["user_id"]), "admin")
    assert verified["email_verified_at"] and verified["role"] == "admin"
    assert store.get_user_by_email(address)["user_id"] == user["user_id"]


def test_only_unverified_accounts_have_their_pending_password_replaced(store):
    user = store.create_user(email(), "old", "A")
    store.update_pending(str(user["user_id"]), "new", "B")
    assert store.get_user(str(user["user_id"]))["password_hash"] == "new"
    store.mark_verified(str(user["user_id"]), "user")
    store.update_pending(str(user["user_id"]), "hijack", "C")
    assert store.get_user(str(user["user_id"]))["password_hash"] == "new"


def test_a_code_is_replaced_by_the_next_one_and_attempts_reset(store):
    address, later = email(), datetime.now(UTC) + timedelta(minutes=10)
    store.put_otp(address, "register", "h1", later)
    assert store.bump_otp_attempts(address, "register") == 1
    assert store.bump_otp_attempts(address, "register") == 2
    store.put_otp(address, "register", "h2", later)
    row = store.get_otp(address, "register")
    assert row["code_hash"] == "h2" and row["attempts"] == 0
    store.delete_otp(address, "register")
    assert (
        store.get_otp(address, "register") is None
        and store.bump_otp_attempts(address, "register") == 0
    )


def test_register_and_reset_codes_are_kept_apart(store):
    address, later = email(), datetime.now(UTC) + timedelta(minutes=10)
    store.put_otp(address, "register", "r", later)
    store.put_otp(address, "reset", "p", later)
    assert (
        store.get_otp(address, "register")["code_hash"] == "r"
        and store.get_otp(address, "reset")["code_hash"] == "p"
    )


def test_sessions_can_be_listed_and_revoked_selectively(store):
    user = store.create_user(email(), "h", "")
    uid, later = str(user["user_id"]), datetime.now(UTC) + timedelta(days=1)
    for name in ("a", "b", "c"):
        store.create_session(uid, hash_token(name), later, "ua", "1.2.3.4")
    assert len(store.list_sessions(uid)) == 3
    assert store.get_session(hash_token("a"))["email"] == user["email"]
    assert store.delete_user_sessions(uid, keep=hash_token("a")) == 2
    assert [s["token_hash"] for s in store.list_sessions(uid)] == [hash_token("a")]
    store.delete_user_sessions(uid)
    assert store.get_session(hash_token("a")) is None


def test_deleting_a_user_removes_their_sessions(store):
    user = store.create_user(email(), "h", "")
    uid = str(user["user_id"])
    store.create_session(uid, hash_token("z"), datetime.now(UTC) + timedelta(days=1), None, None)
    store.conn.execute("DELETE FROM dashboard.app_user WHERE user_id = %s", (uid,))
    assert store.get_session(hash_token("z")) is None


def test_the_rate_limit_ledger_counts_failures_within_a_window(store):
    key = f"auth-test-{uuid.uuid4().hex[:8]}"
    store.record_event("login", key, ok=False)
    store.record_event("login", key, ok=True)
    now = datetime.now(UTC)
    assert len(store.events_since("login", key, now - timedelta(minutes=1))) == 2
    assert (
        len(store.events_since("login", key, now - timedelta(minutes=1), only_failures=True)) == 1
    )
    assert store.events_since("login", key, now + timedelta(minutes=1)) == []
    store.clear_events("login", key)
    assert store.events_since("login", key, now - timedelta(minutes=1)) == []


def test_the_whole_flow_works_end_to_end_on_the_real_store(store):
    mail, address = Mail(), email()
    service = AuthService(store, mail, hasher=FAST, background_mail=False)
    service.register(address, "correct horse battery", "Ada")
    signed = service.verify_registration(address, mail.code(address))
    assert service.authenticate(signed.token)["email"] == address
    assert service.login(address, "correct horse battery").user["email"] == address
    service.logout(signed.token)
    assert service.authenticate(signed.token) is None


def test_a_connection_dropped_by_the_server_is_reopened(store):
    import psycopg

    pid = store.conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
    with psycopg.connect(
        os.environ.get("DBINSIGHT_TEST_DATABASE_URL")
        or os.environ["DBINSIGHT_RESULTS_DATABASE_URL"],
        autocommit=True,
    ) as other:
        other.execute("SELECT pg_terminate_backend(%s)", (pid,))
    assert store.count_verified() >= 0
    assert store.conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"] != pid
