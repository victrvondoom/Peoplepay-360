"""Canonical errors and secret redaction.

No raw SDK exception or stack trace reaches a user: adapters translate into
``GatewayError`` with a canonical ``ErrorCode`` and a sanitized message.
"""
from __future__ import annotations

import re
from enum import Enum


class ErrorCode(str, Enum):
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    CONTEXT_TOO_LARGE = "CONTEXT_TOO_LARGE"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    LOCAL_PROVIDER_OFFLINE = "LOCAL_PROVIDER_OFFLINE"
    PRIVACY_POLICY_BLOCKED = "PRIVACY_POLICY_BLOCKED"
    CUSTOM_ENDPOINT_BLOCKED = "CUSTOM_ENDPOINT_BLOCKED"
    # Not in the brief's list but required to reject bad requests without fallback.
    INVALID_REQUEST = "INVALID_REQUEST"
    POLICY_REJECTED = "POLICY_REJECTED"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    CANCELLED = "CANCELLED"
    NO_ROUTE = "NO_ROUTE"
    SERVER_ERROR = "SERVER_ERROR"


# Failure classes for which trying a different route is semantically correct.
FALLBACK_ELIGIBLE = frozenset({
    ErrorCode.RATE_LIMITED, ErrorCode.QUOTA_EXHAUSTED, ErrorCode.PROVIDER_UNAVAILABLE,
    ErrorCode.MODEL_UNAVAILABLE, ErrorCode.MODEL_NOT_FOUND, ErrorCode.TIMEOUT,
    ErrorCode.SERVER_ERROR, ErrorCode.CONTEXT_TOO_LARGE, ErrorCode.UNSUPPORTED_CAPABILITY,
    ErrorCode.LOCAL_PROVIDER_OFFLINE, ErrorCode.INVALID_RESPONSE,
})

USER_MESSAGES = {
    ErrorCode.INVALID_CREDENTIALS: "The credentials for this provider were rejected.",
    ErrorCode.RATE_LIMITED: "Your selected provider is currently rate limited.",
    ErrorCode.QUOTA_EXHAUSTED: "Your selected provider reports its quota or credits are exhausted.",
    ErrorCode.MODEL_NOT_FOUND: "The selected model was not found on this provider.",
    ErrorCode.MODEL_UNAVAILABLE: "The selected model is currently unavailable.",
    ErrorCode.PROVIDER_UNAVAILABLE: "The selected provider is currently unavailable.",
    ErrorCode.TIMEOUT: "The provider did not answer in time.",
    ErrorCode.CONTEXT_TOO_LARGE: "This conversation is too large for the selected model.",
    ErrorCode.UNSUPPORTED_CAPABILITY: "The selected model cannot do something this request needs.",
    ErrorCode.INVALID_RESPONSE: "The provider returned a response PeoplePay could not use.",
    ErrorCode.LOCAL_PROVIDER_OFFLINE: "The local model runtime is not reachable.",
    ErrorCode.PRIVACY_POLICY_BLOCKED: "The privacy mode blocks every available route for this request.",
    ErrorCode.CUSTOM_ENDPOINT_BLOCKED: "This endpoint address is not allowed on this deployment.",
    ErrorCode.INVALID_REQUEST: "The request was not valid.",
    ErrorCode.POLICY_REJECTED: "A policy rejected this request.",
    ErrorCode.AUTHORIZATION_REQUIRED: "Authorization is required.",
    ErrorCode.CANCELLED: "The request was cancelled.",
    ErrorCode.NO_ROUTE: "No connected model satisfies this request.",
    ErrorCode.SERVER_ERROR: "The provider reported an internal error.",
}


_PATTERNS = [
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[^\s,;\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-~+/=]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), "[REDACTED]"),
    (re.compile(r"\bnvapi-[A-Za-z0-9_\-]{8,}"), "[REDACTED]"),
    (re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{12,}"), "[REDACTED]"),
    (re.compile(r"(?i)(x-api-key|api[-_]?key|secret[-_]?access[-_]?key|session[-_]?token|token|password)(\s*[\"']?\s*[:=]\s*[\"']?)[^\s,;\"'&]+"), r"\1\2[REDACTED]"),
    (re.compile(r"(?i)([?&](?:key|api_key|token|access_token|signature|x-amz-signature)=)[^&\s]+"), r"\1[REDACTED]"),
]


def redact(text: object, *, known_secrets: tuple[str, ...] = (), limit: int = 500) -> str:
    """Strip credentials from text bound for logs or users; also truncates."""
    out = str(text)
    for secret in known_secrets:
        if secret and len(secret) >= 4:
            out = out.replace(secret, "[REDACTED]")
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out[:limit]


class GatewayError(Exception):
    """A canonical, sanitized failure. ``detail`` never contains secrets."""

    def __init__(self, code: ErrorCode, detail: str = "", *, retry_after: float | None = None,
                 http_status: int | None = None, provider_code: str | None = None,
                 extra: dict | None = None):
        self.code = code
        self.extra: dict = dict(extra or {})   # structured UI hints: alternatives, ask_privacy_change, ...
        self.detail = redact(detail)
        self.retry_after = retry_after
        self.http_status = http_status
        self.provider_code = redact(provider_code or "", limit=80) or None
        super().__init__(f"{code.value}: {self.detail}" if self.detail else code.value)

    @property
    def user_message(self) -> str:
        return USER_MESSAGES.get(self.code, "The request failed.")

    @property
    def fallback_eligible(self) -> bool:
        return self.code in FALLBACK_ELIGIBLE

    def to_dict(self) -> dict:
        return {"code": self.code.value, "message": self.user_message, "detail": self.detail,
                "retry_after": self.retry_after, "provider_code": self.provider_code, **self.extra}
