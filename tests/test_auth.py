"""Tests for gateway caller identity.

Before `gateway/auth.py` the gateway trusted `X-Beacon-User` exactly as sent, so
anyone could claim to be anyone.  These tests pin the four properties that
change:

*   a valid token resolves to its user
*   a **forged** user id fails the signature
*   an **expired** token is refused
*   in VERIFIED mode the bare header is ignored entirely, so it cannot be used
    to bypass the very check the token exists to perform

and the one property that deliberately does not change: with no secret set,
local development keeps working -- loudly, via `auth_mode()`.
"""

from __future__ import annotations

import base64

import pytest

from gateway.auth import (
    SECRET_ENV,
    AuthMode,
    InvalidToken,
    auth_mode,
    issue_token,
    verify_caller,
    verify_token,
)

SECRET = "test-secret-not-for-production"


@pytest.fixture()
def verified(monkeypatch):
    monkeypatch.setenv(SECRET_ENV, SECRET)


@pytest.fixture()
def open_mode(monkeypatch):
    monkeypatch.delenv(SECRET_ENV, raising=False)


def _retag(token: str, user_id: str) -> str:
    """Swap the user id but keep the original signature -- the obvious forgery."""
    parts = token.split(".")
    forged_user = base64.urlsafe_b64encode(user_id.encode()).decode().rstrip("=")
    return ".".join([parts[0], forged_user, parts[2], parts[3]])


class TestMode:
    def test_a_secret_means_verified_mode(self, verified):
        assert auth_mode() is AuthMode.VERIFIED

    def test_no_secret_means_open_mode(self, open_mode):
        assert auth_mode() is AuthMode.OPEN

    def test_an_empty_secret_is_not_a_secret(self, monkeypatch):
        """An empty env var is a misconfiguration, not a valid key."""
        monkeypatch.setenv(SECRET_ENV, "")
        assert auth_mode() is AuthMode.OPEN


class TestTokenRoundTrip:
    def test_a_fresh_token_verifies_to_its_user(self, verified):
        assert verify_token(issue_token("user-a")) == "user-a"

    def test_a_bearer_header_resolves_the_caller(self, verified):
        token = issue_token("user-a")
        assert verify_caller(authorization=f"Bearer {token}", user_header=None) == (
            "user-a"
        )

    def test_the_scheme_is_case_insensitive(self, verified):
        token = issue_token("user-a")
        assert verify_caller(authorization=f"bearer {token}", user_header=None) == (
            "user-a"
        )

    def test_a_unicode_user_id_survives(self, verified):
        """Ids are base64url of UTF-8, so a non-ASCII id must round-trip."""
        assert verify_token(issue_token("பயனர்-1")) == "பயனர்-1"

    def test_issuing_without_a_secret_raises_rather_than_faking_one(self, open_mode):
        """A token-shaped string that verifies nothing is worse than an error."""
        with pytest.raises(RuntimeError, match=SECRET_ENV):
            issue_token("user-a")

    def test_an_empty_user_id_is_refused(self, verified):
        with pytest.raises(ValueError, match="user_id is required"):
            issue_token("   ")

    def test_a_non_positive_ttl_is_refused(self, verified):
        """A token with no lifetime is an eternal token."""
        with pytest.raises(ValueError, match="ttl_seconds must be positive"):
            issue_token("user-a", ttl_seconds=0)


class TestForgery:
    """The point of signing."""

    def test_swapping_the_user_id_breaks_the_signature(self, verified):
        forged = _retag(issue_token("user-a"), "user-victim")
        with pytest.raises(InvalidToken, match="signature does not verify"):
            verify_token(forged)

    def test_a_forged_token_resolves_to_nobody(self, verified):
        forged = _retag(issue_token("user-a"), "user-victim")
        assert verify_caller(authorization=f"Bearer {forged}", user_header=None) is None

    def test_extending_the_expiry_breaks_the_signature(self, verified):
        """The signature covers the expiry, so it cannot be extended alone."""
        parts = issue_token("user-a", ttl_seconds=60).split(".")
        parts[2] = str(int(parts[2]) + 86400)
        with pytest.raises(InvalidToken):
            verify_token(".".join(parts))

    def test_a_token_signed_with_another_secret_is_refused(self, monkeypatch):
        monkeypatch.setenv(SECRET_ENV, "secret-one")
        token = issue_token("user-a")
        monkeypatch.setenv(SECRET_ENV, "secret-two")
        with pytest.raises(InvalidToken):
            verify_token(token)

    @pytest.mark.parametrize(
        "bad",
        ["", "garbage", "v1.only.three", "v2.dXNlci1h.99999999999.sig", "....."],
    )
    def test_malformed_tokens_are_refused(self, verified, bad):
        with pytest.raises(InvalidToken):
            verify_token(bad)

    def test_a_malformed_token_does_not_leak_which_check_failed(self, verified):
        """One exception type for every rejection, so probing learns little."""
        for bad in ("garbage", _retag(issue_token("user-a"), "x")):
            with pytest.raises(InvalidToken):
                verify_token(bad)


class TestExpiry:
    def test_an_expired_token_is_refused(self, verified):
        token = issue_token("user-a", ttl_seconds=60, now=0)
        with pytest.raises(InvalidToken, match="expired"):
            verify_token(token, now=61)

    def test_a_token_is_valid_up_to_its_expiry(self, verified):
        token = issue_token("user-a", ttl_seconds=60, now=0)
        assert verify_token(token, now=59) == "user-a"

    def test_expiry_is_exclusive_at_the_boundary(self, verified):
        """At exactly the expiry second the token is already dead."""
        token = issue_token("user-a", ttl_seconds=60, now=0)
        with pytest.raises(InvalidToken, match="expired"):
            verify_token(token, now=60)

    def test_an_expired_token_resolves_to_nobody(self, verified):
        token = issue_token("user-a", ttl_seconds=60, now=0)
        assert (
            verify_caller(authorization=f"Bearer {token}", user_header=None, now=61)
            is None
        )


class TestHeaderCannotBypassTheToken:
    """The property that makes the whole thing worth having."""

    def test_the_bare_header_is_ignored_in_verified_mode(self, verified):
        assert verify_caller(authorization=None, user_header="user-impostor") is None

    def test_the_header_cannot_override_a_valid_token(self, verified):
        """A caller with a real token cannot re-label themselves via the header."""
        token = issue_token("user-a")
        assert (
            verify_caller(authorization=f"Bearer {token}", user_header="user-victim")
            == "user-a"
        )

    def test_a_missing_authorization_header_is_unauthenticated(self, verified):
        assert verify_caller(authorization=None, user_header=None) is None

    def test_a_non_bearer_scheme_is_refused(self, verified):
        token = issue_token("user-a")
        assert verify_caller(authorization=f"Basic {token}", user_header=None) is None

    def test_a_bearer_with_no_token_is_refused(self, verified):
        assert verify_caller(authorization="Bearer ", user_header=None) is None


class TestOpenMode:
    """Local development must keep working, but visibly."""

    def test_the_bare_header_is_accepted_without_a_secret(self, open_mode):
        assert verify_caller(authorization=None, user_header="user-a") == "user-a"

    def test_whitespace_is_not_an_identity(self, open_mode):
        assert verify_caller(authorization=None, user_header="   ") is None

    def test_no_header_is_still_unauthenticated(self, open_mode):
        assert verify_caller(authorization=None, user_header=None) is None

    def test_verify_token_refuses_to_run_without_a_secret(self, open_mode):
        """Better to raise than to silently accept anything in open mode."""
        with pytest.raises(RuntimeError, match=SECRET_ENV):
            verify_token("v1.x.1.y")


class TestGatewayReportsTheMode:
    """An OPEN deployment should be discoverable, not silent."""

    def test_health_says_verified_when_a_secret_is_set(self, verified):
        from gateway.app import GatewayState

        auth = GatewayState(capabilities={}).integrations()["auth"]
        assert auth["mode"] == "VERIFIED"

    def test_health_warns_when_identity_is_unverified(self, open_mode):
        from gateway.app import GatewayState

        auth = GatewayState(capabilities={}).integrations()["auth"]
        assert auth["mode"] == "OPEN"
        assert "unverified" in auth["detail"]
