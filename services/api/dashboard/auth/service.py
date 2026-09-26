"""The account flows. Everything security-relevant is decided here, against a store interface, so
it can be tested without a database or a mail server.

Registration:    register -> (email a code) -> verify -> signed in
Sign-in:         login (email + password); a correct password on an unverified account re-sends a code
Forgot password: forgot -> (email a code) -> reset -> signed out everywhere, sign in again

Rules that hold throughout:
* A code is six digits, valid 10 minutes, tried at most 5 times, and stored only as an HMAC.
* Requests that send a code are rate-limited per address whether or not the account exists, and
  answer the same either way, so the endpoints cannot be used to find out who has an account.
* A wrong password and an unknown email look identical, and take the same time (a dummy hash).
* Repeated failures lock an address out for a while.
* Changing or resetting a password ends the other sessions.
"""

import hashlib
import logging
import math
import re
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from . import mailer as messages
from . import otp, passwords
from .mailer import Mailer

log = logging.getLogger("dbinsight.auth")

SESSION_TTL = timedelta(days=30)
TOUCH_EVERY = timedelta(minutes=10)
LOGIN_WINDOW = timedelta(minutes=15)
MAX_LOGIN_FAILURES_PER_EMAIL = 5
MAX_LOGIN_FAILURES_PER_IP = 25
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    """A refusal that the API returns as `{code, message, ...}` with an HTTP status."""

    def __init__(self, code: str, message: str, status: int = 400, **extra: Any) -> None:
        super().__init__(message)
        self.code, self.message, self.status, self.extra = code, message, status, extra


class Store(Protocol):  # the subset of AuthStore the service uses
    def secret(self) -> bytes: ...
    def get_user_by_email(self, email: str) -> dict[str, Any] | None: ...
    def get_user(self, user_id: str) -> dict[str, Any] | None: ...
    def create_user(self, email: str, password_hash: str, name: str) -> dict[str, Any]: ...
    def update_pending(self, user_id: str, password_hash: str, name: str) -> None: ...
    def count_verified(self) -> int: ...
    def mark_verified(self, user_id: str, role: str) -> dict[str, Any]: ...
    def set_password(self, user_id: str, password_hash: str) -> None: ...
    def set_name(self, user_id: str, name: str) -> None: ...
    def put_otp(self, email: str, purpose: str, code_hash: str, expires_at: datetime) -> None: ...
    def get_otp(self, email: str, purpose: str) -> dict[str, Any] | None: ...
    def bump_otp_attempts(self, email: str, purpose: str) -> int: ...
    def delete_otp(self, email: str, purpose: str) -> None: ...
    def create_session(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip: str | None,
    ) -> None: ...
    def get_session(self, token_hash: str) -> dict[str, Any] | None: ...
    def touch_session(self, token_hash: str) -> None: ...
    def delete_session(self, token_hash: str) -> None: ...
    def delete_user_sessions(self, user_id: str, keep: str | None = None) -> int: ...
    def list_sessions(self, user_id: str) -> list[dict[str, Any]]: ...
    def record_event(self, kind: str, key: str, ok: bool = True) -> None: ...
    def events_since(
        self, kind: str, key: str, since: datetime, only_failures: bool = False
    ) -> list[datetime]: ...
    def clear_events(self, kind: str, key: str) -> None: ...


@dataclass(frozen=True)
class SignedIn:
    token: str
    expires_at: datetime
    user: dict[str, Any]
    became_admin: bool = False


def normalize_email(email: str) -> str:
    cleaned = (email or "").strip().lower()
    if len(cleaned) > 254 or not EMAIL_RE.match(cleaned):
        raise AuthError("invalid_email", "Enter a valid email address.")
    return cleaned


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["user_id"]),
        "email": row["email"],
        "name": row.get("name") or "",
        "role": row["role"],
        "created_at": row.get("user_created_at") or row.get("created_at"),
        # Scanning a folder on the server is a power the operator holds, not every account.
        "can_scan_local": row["role"] == "admin",
    }


class AuthService:
    def __init__(
        self,
        store: Store,
        mailer: Mailer,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        hasher: Callable[[str], str] = passwords.hash_password,
        admin_emails: tuple[str, ...] = (),
        background_mail: bool = True,
    ) -> None:
        self.store, self.mailer, self.now, self.hasher = store, mailer, clock, hasher
        self.admin_emails = tuple(e.lower() for e in admin_emails)
        self.background_mail = background_mail

    # ---- helpers ---------------------------------------------------------

    def _send(self, to: str, message: tuple[str, str, str]) -> None:
        subject, text, html = message

        def deliver() -> None:
            try:
                self.mailer.send(to, subject, text, html)
            except Exception:  # a broken mail server must not break the request or leak state
                log.exception("could not send email to %s", to)

        if self.background_mail:
            threading.Thread(target=deliver, daemon=True).start()
        else:
            deliver()

    def _throttle_send(self, purpose: str, email: str) -> None:
        """Cooldown and hourly cap on code requests, applied whether or not the account exists."""
        kind, now = f"otp_send:{purpose}", self.now()
        recent = self.store.events_since(kind, email, now - timedelta(hours=1))
        if recent and now - max(recent) < otp.RESEND_COOLDOWN:
            wait = math.ceil((otp.RESEND_COOLDOWN - (now - max(recent))).total_seconds())
            raise AuthError(
                "cooldown",
                f"Please wait {wait} seconds before asking for another code.",
                429,
                retry_after=wait,
            )
        if len(recent) >= otp.MAX_SENDS_PER_HOUR:
            raise AuthError(
                "too_many_requests",
                "Too many codes requested. Try again in an hour.",
                429,
                retry_after=3600,
            )
        self.store.record_event(kind, email)

    def _issue_otp(self, email: str, purpose: str) -> None:
        code = otp.new_code()
        self.store.put_otp(
            email,
            purpose,
            otp.code_hash(self.store.secret(), email, purpose, code),
            self.now() + otp.TTL,
        )
        self._send(email, messages.otp_message(purpose, code, int(otp.TTL.total_seconds() // 60)))

    def _check_otp(self, email: str, purpose: str, code: str) -> None:
        row = self.store.get_otp(email, purpose)
        if row is None:
            raise AuthError("invalid_code", "That code is not right. Request a new one.")
        if row["expires_at"] <= self.now():
            self.store.delete_otp(email, purpose)
            raise AuthError("code_expired", "That code has expired. Request a new one.")
        if row["attempts"] >= otp.MAX_ATTEMPTS:
            self.store.delete_otp(email, purpose)
            raise AuthError("too_many_attempts", "Too many wrong codes. Request a new one.", 429)
        if not otp.matches(self.store.secret(), email, purpose, otp.clean(code), row["code_hash"]):
            used = self.store.bump_otp_attempts(email, purpose)
            left = otp.MAX_ATTEMPTS - used
            if left <= 0:
                self.store.delete_otp(email, purpose)
                raise AuthError(
                    "too_many_attempts", "Too many wrong codes. Request a new one.", 429
                )
            raise AuthError(
                "invalid_code",
                f"That code is not right. {left} {'try' if left == 1 else 'tries'} left.",
                attempts_left=left,
            )
        self.store.delete_otp(email, purpose)

    def _new_session(
        self, user_id: str, ip: str | None, user_agent: str | None
    ) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(32)
        expires = self.now() + SESSION_TTL
        self.store.create_session(user_id, hash_token(token), expires, user_agent, ip)
        return token, expires

    def _sent(self, email: str) -> dict[str, Any]:
        return {
            "email": email,
            "resend_after": int(otp.RESEND_COOLDOWN.total_seconds()),
            "expires_in": int(otp.TTL.total_seconds()),
        }

    def _admin_role(self, email: str, current: str) -> str:
        return (
            "admin" if email in self.admin_emails or self.store.count_verified() == 0 else current
        )

    # ---- registration ----------------------------------------------------

    def register(self, email: str, password: str, name: str = "") -> dict[str, Any]:
        email = normalize_email(email)
        problems = passwords.policy_errors(password, email)
        if problems:
            raise AuthError("weak_password", problems[0], 422, problems=problems)
        self._throttle_send("register", email)
        user = self.store.get_user_by_email(email)
        if user and user["email_verified_at"] and not user["disabled"]:
            self._send(email, messages.already_registered_message())
        elif not (user and user["disabled"]):
            hashed = self.hasher(password)
            clean_name = (name or "").strip()[:80]
            if user:
                self.store.update_pending(str(user["user_id"]), hashed, clean_name)
            else:
                self.store.create_user(email, hashed, clean_name)
            self._issue_otp(email, "register")
        return self._sent(email)

    def resend(self, email: str, purpose: str) -> dict[str, Any]:
        if purpose not in otp.PURPOSES:
            raise AuthError("bad_request", "Unknown request.")
        email = normalize_email(email)
        self._throttle_send(purpose, email)
        user = self.store.get_user_by_email(email)
        eligible = (
            bool(user)
            and not user["disabled"]
            and bool(user["email_verified_at"]) == (purpose == "reset")
        )
        if eligible:
            self._issue_otp(email, purpose)
        return self._sent(email)

    def verify_registration(
        self, email: str, code: str, ip: str | None = None, user_agent: str | None = None
    ) -> SignedIn:
        email = normalize_email(email)
        self._check_otp(email, "register", code)
        user = self.store.get_user_by_email(email)
        if user is None or user["disabled"]:
            raise AuthError("invalid_code", "That code is not right. Request a new one.")
        role = self._admin_role(email, user["role"])
        verified = self.store.mark_verified(str(user["user_id"]), role)
        token, expires = self._new_session(str(verified["user_id"]), ip, user_agent)
        return SignedIn(
            token,
            expires,
            public_user(verified),
            became_admin=role == "admin" and user["role"] != "admin",
        )

    # ---- signing in ------------------------------------------------------

    def _lockout(self, email: str, ip: str | None) -> None:
        since = self.now() - LOGIN_WINDOW
        by_email = self.store.events_since("login", email, since, only_failures=True)
        by_ip = (
            self.store.events_since("login_ip", ip or "-", since, only_failures=True) if ip else []
        )
        if len(by_email) >= MAX_LOGIN_FAILURES_PER_EMAIL or len(by_ip) >= MAX_LOGIN_FAILURES_PER_IP:
            oldest = min(by_email or by_ip)
            wait = max(1, int((oldest + LOGIN_WINDOW - self.now()).total_seconds()))
            raise AuthError(
                "locked",
                f"Too many failed attempts. Try again in {max(1, math.ceil(wait / 60))} minutes.",
                429,
                retry_after=wait,
            )

    def login(
        self, email: str, password: str, ip: str | None = None, user_agent: str | None = None
    ) -> SignedIn:
        email = normalize_email(email)
        self._lockout(email, ip)
        user = self.store.get_user_by_email(email)
        stored = user["password_hash"] if user else passwords.dummy_hash()
        valid = (
            passwords.verify_password(password, stored)
            and user is not None
            and not user["disabled"]
        )
        if not valid:
            self.store.record_event("login", email, ok=False)
            if ip:
                self.store.record_event("login_ip", ip, ok=False)
            raise AuthError("invalid_credentials", "The email or password is not right.", 401)
        assert user is not None
        if not user["email_verified_at"]:
            try:
                self._throttle_send("register", email)
                self._issue_otp(email, "register")
            except AuthError:
                pass  # a code was sent moments ago; the verify page explains
            raise AuthError(
                "email_not_verified",
                "Verify your email to finish signing up. We sent you a code.",
                403,
                email=email,
            )
        self.store.clear_events("login", email)
        if passwords.needs_rehash(user["password_hash"]):
            self.store.set_password(str(user["user_id"]), self.hasher(password))
        token, expires = self._new_session(str(user["user_id"]), ip, user_agent)
        return SignedIn(token, expires, public_user(user))

    # ---- forgot / reset --------------------------------------------------

    def forgot(self, email: str) -> dict[str, Any]:
        return self.resend(email, "reset")

    def reset(self, email: str, code: str, new_password: str) -> None:
        email = normalize_email(email)
        problems = passwords.policy_errors(new_password, email)
        if problems:
            raise AuthError("weak_password", problems[0], 422, problems=problems)
        self._check_otp(email, "reset", code)
        user = self.store.get_user_by_email(email)
        if user is None or user["disabled"]:
            raise AuthError("invalid_code", "That code is not right. Request a new one.")
        self.store.set_password(str(user["user_id"]), self.hasher(new_password))
        self.store.mark_verified(
            str(user["user_id"]), user["role"]
        )  # they proved control of the inbox
        self.store.delete_user_sessions(str(user["user_id"]))
        self.store.clear_events("login", email)
        self._send(email, messages.password_changed_message())

    # ---- signed-in users -------------------------------------------------

    def authenticate(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        digest = hash_token(token)
        row = self.store.get_session(digest)
        if row is None or row["disabled"] or not row["email_verified_at"]:
            return None
        now = self.now()
        if row["expires_at"] <= now:
            self.store.delete_session(digest)
            return None
        if now - row["last_seen_at"] > TOUCH_EVERY:
            self.store.touch_session(digest)
        return {**public_user(row), "session": digest}

    def logout(self, token: str | None) -> None:
        if token:
            self.store.delete_session(hash_token(token))

    def change_password(
        self, user_id: str, current: str, new: str, keep_session: str | None
    ) -> None:
        user = self.store.get_user(user_id)
        if user is None or not passwords.verify_password(current, user["password_hash"]):
            raise AuthError("invalid_credentials", "Your current password is not right.", 401)
        problems = passwords.policy_errors(new, user["email"])
        if problems:
            raise AuthError("weak_password", problems[0], 422, problems=problems)
        if passwords.verify_password(new, user["password_hash"]):
            raise AuthError(
                "weak_password",
                "Choose a password you have not used just now.",
                422,
                problems=["Choose a different password."],
            )
        self.store.set_password(user_id, self.hasher(new))
        self.store.delete_user_sessions(user_id, keep=keep_session)
        self._send(user["email"], messages.password_changed_message())

    def sign_out_others(self, user_id: str, keep_session: str) -> int:
        return self.store.delete_user_sessions(user_id, keep=keep_session)

    def rename(self, user_id: str, name: str) -> None:
        self.store.set_name(user_id, (name or "").strip()[:80])

    def sessions(self, user_id: str, current: str) -> list[dict[str, Any]]:
        return [
            {
                "created_at": s["created_at"],
                "last_seen_at": s["last_seen_at"],
                "user_agent": s["user_agent"] or "",
                "ip": s["ip"] or "",
                "current": s["token_hash"] == current,
            }
            for s in self.store.list_sessions(user_id)
        ]
