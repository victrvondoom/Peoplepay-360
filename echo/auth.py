"""Reuse PeoplePay caller identity; separate administrator mutation capability."""

import hmac
import os

from fastapi import HTTPException, Request

from gateway.auth import auth_mode, verify_caller


def caller(request: Request) -> str:
    identity = verify_caller(authorization=request.headers.get("Authorization"),
                             user_header=request.headers.get("X-Beacon-User"))
    if not identity:
        raise HTTPException(status_code=401, detail="PeoplePay caller identity is required")
    return identity


def administrator(request: Request) -> str:
    identity = caller(request)
    expected = os.getenv("ECHO_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Extension administration is not configured")
    supplied = request.headers.get("X-Echo-Admin-Token", "")
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="ECHO administrator authorization is required")
    return identity


def identity_mode() -> str:
    return auth_mode().value
