"""Password hashing (scrypt, stdlib) and the password policy.

Hashes are self-describing (`scrypt$N$r$p$salt$hash`), so the work factor can be raised later and
old hashes are upgraded at the next login (`needs_rehash`).
"""

import base64
import hashlib
import hmac
import os
import re

# OWASP's scrypt guidance: N=2^15, r=8, p=3 is an accepted minimum (about 32 MiB, ~0.1 s).
N, R, P = 2**15, 8, 3
SALT_BYTES = 16
KEY_BYTES = 32
MIN_LENGTH = 10
MAX_LENGTH = 128

COMMON = {
    "password", "password1", "password12", "password123", "passw0rd123", "1234567890", "12345678910",
    "qwertyuiop", "qwerty12345", "iloveyou123", "letmein1234", "welcome1234", "admin12345",
    "administrator", "changeme123", "abc1234567", "1q2w3e4r5t", "0123456789", "monkey12345",
    "dragon12345", "football123", "baseball123", "trustno1234", "superman123", "internet123",
}  # fmt: skip


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, dklen=KEY_BYTES, maxmem=256 * 1024 * 1024
    )


def hash_password(password: str, *, n: int = N, r: int = R, p: int = P) -> str:
    salt = os.urandom(SALT_BYTES)
    digest = _derive(password, salt, n, r, p)
    b64 = base64.b64encode
    return f"scrypt${n}${r}${p}${b64(salt).decode()}${b64(digest).decode()}"


def _parse(stored: str) -> tuple[int, int, int, bytes, bytes] | None:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return None
        return int(n), int(r), int(p), base64.b64decode(salt), base64.b64decode(digest)
    except ValueError:
        return None


def verify_password(password: str, stored: str) -> bool:
    parsed = _parse(stored)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    return hmac.compare_digest(_derive(password, salt, n, r, p), expected)


def needs_rehash(stored: str) -> bool:
    parsed = _parse(stored)
    return parsed is None or parsed[:3] != (N, R, P)


_dummy: str | None = None


def dummy_hash() -> str:
    """A hash to check against when the account does not exist, so timing does not reveal it."""
    global _dummy
    if _dummy is None:
        _dummy = hash_password("not-a-real-password")
    return _dummy


def policy_errors(password: str, email: str = "") -> list[str]:
    """Why a password is not acceptable, in words a person can act on. Empty means acceptable."""
    errors = []
    if len(password) < MIN_LENGTH:
        errors.append(f"Use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        errors.append(f"Use at most {MAX_LENGTH} characters.")
    if password.lower() in COMMON or len(set(password)) < 4:
        errors.append("That password is too common or too repetitive.")
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in password.lower():
        errors.append("Do not include your email name in the password.")
    if password and not re.search(r"[A-Za-z]", password) and not re.search(r"\s", password):
        errors.append("Include some letters, or use a longer passphrase.")
    return errors
