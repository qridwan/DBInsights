"""An in-memory Store and a capturing Mailer for testing the account service."""

import itertools
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from api.dashboard.auth import passwords
from api.dashboard.auth.service import AuthService


def uid(n: int) -> str:
    """A valid UUID for the n-th user, as the real database requires."""
    return str(uuid.UUID(int=n))


UID1 = uid(1)
FAST = lambda p: passwords.hash_password(p, n=2**10, r=8, p=1)  # noqa: E731


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.t

    def advance(self, **kw: float) -> None:
        self.t += timedelta(**kw)


class Mail:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html or ""})

    def code(self, to: str | None = None) -> str:
        """The most recent 6-digit code sent (to `to`, if given)."""
        for m in reversed(self.sent):
            if to and m["to"] != to:
                continue
            found = re.search(r"(\d{3}) (\d{3})", m["text"])
            if found:
                return found.group(1) + found.group(2)
        raise AssertionError("no code was sent")

    def to(self, address: str) -> list[dict[str, str]]:
        return [m for m in self.sent if m["to"] == address]


class MemoryStore:
    def __init__(self, clock: Clock) -> None:
        self.clock, self.users, self.otps, self.sessions, self.events = clock, {}, {}, {}, []
        self._ids = itertools.count(1)
        self._secret = b"\x01" * 32

    def secret(self):
        return self._secret  # noqa: E704

    def get_user_by_email(self, email):
        return next((u for u in self.users.values() if u["email"] == email), None)  # noqa: E704

    def get_user(self, uid):
        return self.users.get(uid)  # noqa: E704

    def create_user(self, email, password_hash, name):
        user_id = uid(next(self._ids))
        self.users[user_id] = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "password_hash": password_hash,
            "role": "user",
            "email_verified_at": None,
            "disabled": False,
            "created_at": self.clock(),
        }
        return self.users[user_id]

    def update_pending(self, uid, password_hash, name):
        u = self.users[uid]
        if not u["email_verified_at"]:
            u["password_hash"], u["name"] = password_hash, name

    def count_verified(self):
        return sum(bool(u["email_verified_at"]) for u in self.users.values())  # noqa: E704

    def mark_verified(self, uid, role):
        u = self.users[uid]
        u["email_verified_at"] = u["email_verified_at"] or self.clock()
        u["role"] = role
        return u

    def set_password(self, uid, h):
        self.users[uid]["password_hash"] = h  # noqa: E704

    def set_name(self, uid, name):
        self.users[uid]["name"] = name  # noqa: E704

    def put_otp(self, email, purpose, h, expires_at):
        self.otps[(email, purpose)] = {
            "code_hash": h,
            "expires_at": expires_at,
            "attempts": 0,
            "created_at": self.clock(),
        }

    def get_otp(self, email, purpose):
        return self.otps.get((email, purpose))  # noqa: E704

    def bump_otp_attempts(self, email, purpose):
        row = self.otps.get((email, purpose))
        if not row:
            return 0
        row["attempts"] += 1
        return row["attempts"]

    def delete_otp(self, email, purpose):
        self.otps.pop((email, purpose), None)  # noqa: E704

    def create_session(self, uid, th, expires_at, ua, ip):
        self.sessions[th] = {
            "token_hash": th,
            "user_id": uid,
            "expires_at": expires_at,
            "created_at": self.clock(),
            "last_seen_at": self.clock(),
            "user_agent": ua,
            "ip": ip,
        }

    def get_session(self, th):
        s = self.sessions.get(th)
        if not s:
            return None
        u = self.users[s["user_id"]]
        return {
            **s,
            "email": u["email"],
            "name": u["name"],
            "role": u["role"],
            "disabled": u["disabled"],
            "email_verified_at": u["email_verified_at"],
            "user_created_at": u["created_at"],
        }

    def touch_session(self, th):
        self.sessions[th]["last_seen_at"] = self.clock()  # noqa: E704

    def delete_session(self, th):
        self.sessions.pop(th, None)  # noqa: E704

    def delete_user_sessions(self, uid, keep=None):
        gone = [h for h, s in self.sessions.items() if s["user_id"] == uid and h != keep]
        for h in gone:
            del self.sessions[h]
        return len(gone)

    def list_sessions(self, uid):
        return [s for s in self.sessions.values() if s["user_id"] == uid]  # noqa: E704

    def record_event(self, kind, key, ok=True):
        self.events.append((kind, key, ok, self.clock()))  # noqa: E704

    def events_since(self, kind, key, since, only_failures=False):
        return [
            at
            for k, key2, ok, at in self.events
            if k == kind and key2 == key and at >= since and (not only_failures or not ok)
        ]

    def clear_events(self, kind, key):
        self.events = [e for e in self.events if not (e[0] == kind and e[1] == key)]  # noqa: E704


def make(**kw: Any) -> tuple[AuthService, MemoryStore, Mail, Clock]:
    clock, mail = Clock(), Mail()
    store = MemoryStore(clock)
    service = AuthService(store, mail, clock=clock, hasher=FAST, background_mail=False, **kw)
    return service, store, mail, clock


def sign_in(
    service: AuthService, mail: Mail, email: str, password: str = "correct horse battery"
) -> dict[str, str]:
    """Register and verify an account, and return the Authorization header for it."""
    service.register(email, password, email.split("@")[0])
    signed = service.verify_registration(email, mail.code(email))
    return {"Authorization": f"Bearer {signed.token}"}
