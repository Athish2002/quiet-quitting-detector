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

from src.api.errors import problem
from src.security.identity import KeyRing, Principal, Role, verify_webhook_signature
from src.security.limits import (
    EXPENSIVE_LIMIT,
    EXPENSIVE_WINDOW_SECONDS,
    MAX_BODY_BYTES,
    READ_LIMIT,
    READ_WINDOW_SECONDS,
    RateLimiter,
)
from src.security.policy import SAFE_METHODS, is_public, required_role, uses_hmac

logger = logging.getLogger(__name__)

#: Routes whose cost is an LLM call or a full pipeline run.
_EXPENSIVE_PREFIXES = ("/api/run", "/api/score/", "/api/ingest/natural-language")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # Phase 6 retired the legacy single-file dashboard, which is what forced
    # 'unsafe-inline' -- it carried 2,000 lines of inline script. The Vite build
    # emits external files, so script-src is now 'self' only, and a CSP without
    # 'unsafe-inline' is the difference between a header that stops injected
    # script and one that mostly does not.
    #
    # style-src still allows inline: React sets element styles directly (the
    # sparkline bar heights), and the alternative is a nonce plumbed through
    # every render. Injected CSS is a far narrower problem than injected script.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


def _unauthorised() -> JSONResponse:
    # RFC 9457, matching every other error in the app. Middleware runs before
    # the exception handlers, so these have to build the problem document
    # themselves -- and if they did not, the refusals a caller is MOST likely to
    # meet would be the only responses with a different shape, which defeats the
    # point of having one.
    return problem(
        401,
        "Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden() -> JSONResponse:
    return problem(403, "Insufficient permissions.")


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
        self.reads = RateLimiter(READ_LIMIT, READ_WINDOW_SECONDS)
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
            return _with_headers(problem(413, "Request body too large."))

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

        # Three budgets, because the costs are three different things: a model
        # call, a write, and a file read. One number for all of them is either
        # too loose for the first or too tight for the last.
        if path.startswith(_EXPENSIVE_PREFIXES):
            limiter = self.expensive
        elif method in SAFE_METHODS:
            limiter = self.reads
        else:
            limiter = self.general
        # Limited on identity AND source address: per-IP alone is defeated by a
        # proxy, per-identity alone by never authenticating.
        for bucket in (f"key:{principal.key_id}", f"ip:{_client_ip(request)}"):
            allowed, retry_after = limiter.check(bucket)
            if not allowed:
                return _with_headers(
                    problem(
                        429,
                        "Rate limit exceeded.",
                        headers={"Retry-After": str(retry_after)},
                    )
                )

        request.state.principal = principal
        response = await call_next(request)

        # Record permitted accesses for data endpoints (excluding internal noise like /audit/log or static assets)
        if 200 <= response.status_code < 400 and not path.endswith(("/audit/log", "/metrics", "/favicon.ico")):
            try:
                from src.governance.audit import record_access

                role_str = principal.role.value if hasattr(principal.role, "value") else str(principal.role)
                role_name = "Wellbeing Analyst" if role_str == "analyst" else ("Manager" if role_str == "manager" else "Employee")
                subject = path.split("/")[-1] if ("/employee/" in path or "/person/" in path) else "Cohort"
                record_access(
                    actor=role_name,
                    action=f"{method} {path}",
                    purpose="wellbeing_review",
                    subject_id=subject,
                    outcome="allowed",
                    detail=f"key={principal.key_id}",
                )
            except Exception:
                pass

        return _with_headers(response)


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
