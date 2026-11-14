"""
Forwarder -> backend auth, Sprint 1 scope: a single shared API key via header.

This is the "good enough for Sprint 1" answer from spike #7 — not final
security hardening. mTLS or per-host tokens are reasonable follow-ups once
we have more than one forwarder deployment to manage.
"""

import os

from fastapi import Header, HTTPException, status

API_KEY_ENV_VAR = "AGENTWATCH_API_KEY"


def require_api_key(x_api_key: str = Header(default="")) -> None:
    expected = os.environ.get(API_KEY_ENV_VAR)
    if not expected:
        # Fail closed: an unset key in the environment is a misconfiguration,
        # not an "open" backend.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backend misconfigured: {API_KEY_ENV_VAR} is not set.",
        )
    if x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
