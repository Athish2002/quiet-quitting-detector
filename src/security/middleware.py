# src/security/middleware.py
# The single place every request is authorised (spec 7, blocker B1).
#
# One middleware rather than thirty decorators, for the reason set out in
# src/security/policy.py: a decorator protects the routes somebody remembered to
# decorate. This closes B1 for every route that exists and every route that will
# exist, including the ones added by someone who has never read this file.
#
# Errors returned here are deliberately uninformative. "Authentication required"
# for both a missing key and a wrong one; no hint about which keys exist, which
# roles a path needs, or whether a path exists at all. An attacker learning the
# shape of the authorisation model from 403 vs 404 is a real, if unglamorous,
# information leak.

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.security.identity import KeyRing, Principal, Role, verify_webhook_signature
from src.security.limits import (
    EXPENSIVE_LIMIT,
    EXPENSIVE_WINDOW_SECONDS,
    MAX_BODY_BYTES,
    RateLimiter,
)
from src.security.policy import is_public, required_role, uses_hmac

logger = logging.getLogger(__name__)

#: Routes whose cost is an LLM call or a full pipeline run.
_EXPENSIVE_PREFIXES = ("/api/run", "/api/score/", "/api/ingest/natural-language")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # The bundled UI is one HTML file with inline styles and scripts, so
    # 'unsafe-inline' is required until the Phase 6 React rebuild moves them into
    # separate files. Recorded in docs/LIMITATIONS.md rather than left to be
    # discovered -- a CSP with 'unsafe-inline' stops far less than it appears to.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


def _unauthorised(detail: str = "Authentication required.") -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden() -> JSONResponse:
    return JSONResponse(
        status_code=403, content={"detail": "Insufficient permissions."}
    )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SecurityMiddleware(BaseHTTPMiddleware):
    """Authenticate, authorise, rate-limit and cap every request."""

    def __init__(self, app, keyring: KeyRing | None = None) -> None:
        super().__init__(app)
        self.keyring = keyring or KeyRing()
        self.general = RateLimiter()
        self.expensive = RateLimiter(EXPENSIVE_LIMIT, EXPENSIVE_WINDOW_SECONDS)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        if is_public(path):
            return _with_headers(await call_next(request))

        # Body cap first: refuse to read an oversized payload at all, rather
        # than authenticating and then discovering it.
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return _with_headers(
                JSONResponse(
                    status_code=413, content={"detail": "Request body too large."}
                )
            )

        principal = self.keyring.authenticate(_bearer(request))

        # Webhook ingest is authenticated by an HMAC signature over the body,
        # since the sender is a system that cannot hold a rotating bearer token.
        if principal is None and uses_hmac(path):
            body = await request.body()
            if verify_webhook_signature(body, request.headers.get("X-Signature")):
                principal = Principal(key_id="webhook-hmac", role=Role.MANAGER)
                request.state.body = body

        if principal is None:
            _audit_denial(path, method, "unauthenticated", _client_ip(request))
            return _with_headers(_unauthorised())

        if not principal.can(required_role(method, path)):
            _audit_denial(path, method, principal.key_id, _client_ip(request))
            return _with_headers(_forbidden())

        limiter = (
            self.expensive if path.startswith(_EXPENSIVE_PREFIXES) else self.general
        )
        # Limited on identity AND source address: per-IP alone is defeated by a
        # proxy, per-identity alone by never authenticating.
        for bucket in (f"key:{principal.key_id}", f"ip:{_client_ip(request)}"):
            allowed, retry_after = limiter.check(bucket)
            if not allowed:
                return _with_headers(
                    JSONResponse(
                        status_code=429,
                        content={"detail": "Rate limit exceeded."},
                        headers={"Retry-After": str(retry_after)},
                    )
                )

        request.state.principal = principal
        return _with_headers(await call_next(request))


def _bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.headers.get("X-API-Key") or None


def _with_headers(response):
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


def _audit_denial(path: str, method: str, actor: str, ip: str) -> None:
    """Record a refused request.

    Denials are the entries that matter most in an audit trail: a successful
    read is expected traffic, while a pattern of refusals is the only early
    signal that someone is trying doors. Never raises -- see governance.audit.
    """
    try:
        from src.governance.audit import record_access

        record_access(
            actor=actor,
            action=f"{method} {path}",
            purpose="access_control",
            outcome="denied",
            detail=f"source={ip}",
        )
    except Exception:
        logger.warning("Could not record an access denial.")
