"""Caller identity for the gateway: a verified token, or an honest open mode.

Before this module the gateway trusted ``X-Beacon-User`` exactly as sent, which
means anybody could claim to be anybody.  Ownership checks on the aggregate
(``assert_owned_by``) still applied, so one user could not read another's
transaction *by accident* -- but they could by simply typing a different header.

What this adds is verification: a bearer token whose user id is signed with a
shared secret, so the id cannot be edited without invalidating the signature.

    v1.<user-id, base64url>.<expiry, unix seconds>.<HMAC-SHA256, base64url>

Deliberate properties:

*   **HMAC, not an unsigned claim.** The signature covers the id *and* the
    expiry, so neither can be changed independently.
*   **Constant-time comparison.** ``hmac.compare_digest``, so a wrong signature
    does not leak how nearly right it was through timing.
*   **Expiry is mandatory.** A token without one is refused rather than treated
    as eternal.
*   **Open mode is loud, not silent.** With no ``BEACON_GATEWAY_SECRET`` set the
    gateway keeps accepting a bare header so local development is unaffected,
    but ``auth_mode()`` reports ``OPEN`` and the health payload says so.  A
    deployment that forgets the secret can be *seen* to have forgotten it.

This is symmetric-secret auth for a first-party gateway.  It is not OIDC and does
not pretend to be: there is no issuer, no audience, no key rotation and no
revocation list.  When this fronts anything public, replace ``verify_caller``
with a real verifier -- that is why identity lives in one function.
"""

from __future__ import annotations

import base64
import hmac
import os
import time
from enum import StrEnum
from hashlib import sha256

__all__ = [
    "DEFAULT_TTL_SECONDS",
    "SECRET_ENV",
    "TOKEN_PREFIX",
    "AuthMode",
    "InvalidToken",
    "auth_mode",
    "issue_token",
    "verify_caller",
    "verify_token",
]

SECRET_ENV = "BEACON_GATEWAY_SECRET"
TOKEN_PREFIX = "v1"

#: How long a freshly issued token lasts by default.
DEFAULT_TTL_SECONDS = 3600


class AuthMode(StrEnum):
    """Which identity regime the gateway is running under."""

    VERIFIED = "VERIFIED"
    """A secret is configured; tokens are required and checked."""

    OPEN = "OPEN"
    """No secret configured.  A bare header is accepted.  Local use only."""


class InvalidToken(ValueError):
    """Raised when a token is absent, malformed, expired or badly signed.

    One exception type for every failure, so a caller cannot branch on *which*
    check failed and narrow down a forgery attempt.
    """


def _secret() -> bytes | None:
    raw = os.getenv(SECRET_ENV)
    return raw.encode("utf-8") if raw else None


def auth_mode() -> AuthMode:
    """Report the current regime.  Safe to expose; it names no secret."""
    return AuthMode.VERIFIED if _secret() else AuthMode.OPEN


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(user_id: str, expires_at: int, secret: bytes) -> str:
    payload = f"{TOKEN_PREFIX}.{_b64(user_id.encode('utf-8'))}.{expires_at}"
    digest = hmac.new(secret, payload.encode("ascii"), sha256).digest()
    return _b64(digest)


def issue_token(
    user_id: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: int | None = None,
) -> str:
    """Mint a token for ``user_id``.

    Raises ``RuntimeError`` when no secret is configured, rather than returning
    something token-shaped that verifies nothing.
    """
    secret = _secret()
    if secret is None:
        raise RuntimeError(
            f"cannot issue a token without {SECRET_ENV}; "
            "the gateway is running in OPEN mode"
        )
    if not user_id or not user_id.strip():
        raise ValueError("user_id is required")
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive; a token needs a lifetime")
    expires_at = int(now if now is not None else time.time()) + ttl_seconds
    signature = _sign(user_id, expires_at, secret)
    return f"{TOKEN_PREFIX}.{_b64(user_id.encode('utf-8'))}.{expires_at}.{signature}"


def verify_token(token: str, *, now: int | None = None) -> str:
    """Return the user id a token proves, or raise ``InvalidToken``."""
    secret = _secret()
    if secret is None:
        raise RuntimeError(
            f"verify_token requires {SECRET_ENV}; check auth_mode() first"
        )

    parts = (token or "").split(".")
    if len(parts) != 4 or parts[0] != TOKEN_PREFIX:
        raise InvalidToken("token is not a valid v1 gateway token")

    _, user_b64, expiry_text, signature = parts
    try:
        user_id = _unb64(user_b64).decode("utf-8")
        expires_at = int(expiry_text)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidToken("token is not a valid v1 gateway token") from exc

    expected = _sign(user_id, expires_at, secret)
    # Constant time: a near-miss signature must not be distinguishable by timing.
    if not hmac.compare_digest(expected, signature):
        raise InvalidToken("token signature does not verify")

    # Signature is checked before expiry, so the expiry message cannot tell an
    # attacker that their forged signature was otherwise acceptable.
    if int(now if now is not None else time.time()) >= expires_at:
        raise InvalidToken("token has expired")

    if not user_id.strip():
        raise InvalidToken("token carries no user id")
    return user_id


def verify_caller(
    *,
    authorization: str | None,
    user_header: str | None,
    now: int | None = None,
) -> str | None:
    """Resolve the calling user, or ``None`` when the request is unauthenticated.

    In ``VERIFIED`` mode only a good ``Authorization: Bearer <token>`` counts,
    and ``X-Beacon-User`` is ignored entirely -- otherwise the header would be a
    trivial bypass of the very thing the token exists to prevent.

    In ``OPEN`` mode the bare header is accepted, because refusing it would break
    local development for no security gain: there is no secret to check against.
    """
    if auth_mode() is AuthMode.VERIFIED:
        if not authorization:
            return None
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        try:
            return verify_token(token.strip(), now=now)
        except InvalidToken:
            return None
    return (user_header or "").strip() or None
