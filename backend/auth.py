"""Authentication helpers for Campus Customs.

Two concerns live here, kept away from the route handlers in main.py:

1. Password hashing. New accounts are hashed with bcrypt. The three seeded
   users carry a legacy ``pbkdf2_sha256$salt$hash`` value, so we also verify
   that format — a login with a legacy hash succeeds and is transparently
   re-hashed with bcrypt on the way through.

2. Session tokens. We issue a stateless HMAC-signed token rather than pull in a
   session store or a JWT library. The token carries the user id and an expiry;
   the signature is what makes it unforgeable. The signing key comes from the
   CAMPUS_CUSTOMS_SECRET environment variable, with a dev fallback.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

import bcrypt

# bcrypt truncates silently at 72 bytes; reject longer inputs rather than let
# two different passwords collide into the same hash.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8

# A dev-only default. In anything real this must come from the environment;
# rotating it invalidates every outstanding session, which is the point.
_SECRET = os.environ.get("CAMPUS_CUSTOMS_SECRET", "dev-only-campus-customs-secret").encode()
_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60  # one week

# Iteration counts to try for the legacy 3-part pbkdf2 hashes, which do not
# carry their own iteration count. 120_000 is what the seeded accounts use;
# the rest are common framework defaults, kept as a fallback.
_LEGACY_PBKDF2_ITERATIONS = (120_000, 100_000, 150_000, 180_000, 260_000, 310_000, 600_000)


# --------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Return a bcrypt hash (its own salt is embedded in the output string)."""
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def _verify_legacy_pbkdf2(password: str, stored: str) -> bool:
    """Verify the seeded ``pbkdf2_sha256$salt$hexdigest`` format.

    Compared in constant time. Unknown or malformed values return False rather
    than raising, so a bad row can never crash a login.
    """
    try:
        algorithm, salt, expected_hex = stored.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    # This 3-part format does not embed an iteration count, so we try the
    # values the seed data is known to use. The seeded accounts (including
    # test@campuscustoms.yale.edu) were hashed at 120_000 iterations; the
    # others cover common Django/Werkzeug defaults.
    for iterations in _LEGACY_PBKDF2_ITERATIONS:
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
        ).hex()
        if hmac.compare_digest(expected_hex, candidate):
            return True
    return False


def verify_password(password: str, stored_hash: str) -> bool:
    """True if ``password`` matches ``stored_hash`` (bcrypt or legacy pbkdf2)."""
    if not stored_hash:
        return False
    if stored_hash.startswith("$2"):  # bcrypt: $2a$ / $2b$ / $2y$
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        except ValueError:
            return False
    if stored_hash.startswith("pbkdf2_"):
        return _verify_legacy_pbkdf2(password, stored_hash)
    return False


def needs_rehash(stored_hash: str) -> bool:
    """A non-bcrypt hash should be upgraded after a successful login."""
    return not stored_hash.startswith("$2")


# --------------------------------------------------------------------------
# Session tokens (stateless, HMAC-signed)
# --------------------------------------------------------------------------


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def issue_token(user_id: int) -> str:
    """Create a signed ``<payload>.<signature>`` token for a user."""
    payload = {"uid": user_id, "exp": int(time.time()) + _TOKEN_TTL_SECONDS}
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64url_encode(hmac.new(_SECRET, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_token(token: str) -> int | None:
    """Return the user id for a valid, unexpired token, else None."""
    try:
        body, signature = token.split(".", 1)
    except (ValueError, AttributeError):
        return None

    expected = _b64url_encode(hmac.new(_SECRET, body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        payload: dict[str, Any] = json.loads(_b64url_decode(body))
    except (ValueError, json.JSONDecodeError):
        return None

    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    uid = payload.get("uid")
    return int(uid) if isinstance(uid, int) else None
