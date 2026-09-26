"""One-time codes: generation, hashing, and the limits around them.

A code is six digits, valid for ten minutes, and can be tried five times. It is stored only as an
HMAC keyed with a server secret and bound to the email and purpose, so a database leak does not
yield usable codes and a code for one purpose or address never works for another.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_SENDS_PER_HOUR = 5
PURPOSES = ("register", "reset")


def new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def code_hash(secret: bytes, email: str, purpose: str, code: str) -> str:
    message = f"{purpose}\x00{email}\x00{code}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def matches(secret: bytes, email: str, purpose: str, code: str, stored: str) -> bool:
    return hmac.compare_digest(code_hash(secret, email, purpose, code), stored)


def clean(code: str) -> str:
    """Accept what people paste: spaces and dashes are ignored."""
    return "".join(ch for ch in code if ch.isdigit())
