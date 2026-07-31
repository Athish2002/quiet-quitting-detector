# src/security/policy.py
# Which role each route needs -- as a DEFAULT-DENY table (spec 7, blocker B1).
#
# The design decision that matters here is default-deny, and it is the same one
# `config/data_allowlist.json` already makes about data. A per-route decorator
# protects the routes somebody remembered to decorate; the thirty-first route,
# added in a hurry six months from now, is unprotected and nothing says so.
# B1 is on the blocker list because `POST /api/memory/clear` wiped everything
# with no authentication at all -- not because anyone decided it should be open,
# but because nothing forced the question to be asked.
#
# So: everything requires authentication unless it appears in PUBLIC_PATHS, and
# anything that mutates requires at least MANAGER unless it is listed as
# admin-only. A new route is protected the moment it exists, and making it
# public is a visible edit to this file rather than an omission.

from __future__ import annotations

import re

from src.security.identity import Role

#: Methods that do not change state. Still authenticated -- this system's reads
#: ARE the sensitive operation, since the whole product is looking at people.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: Paths served to anyone. Deliberately tiny: the static UI, the health probe,
#: and the OpenAPI documents. Nothing here reveals anything about an employee.
PUBLIC_PATHS = frozenset(
    {
        "/",
        "/favicon.ico",
        "/healthz",
        "/readyz",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/docs/oauth2-redirect",
    }
)

#: Static assets, matched by prefix.
PUBLIC_PREFIXES = ("/static/", "/assets/")

#: Extensions the bundled single-page UI needs before a key can be entered.
PUBLIC_SUFFIXES = (".html", ".css", ".js", ".png", ".jpg", ".svg", ".ico", ".woff2")

#: Routes that destroy data or spend money. ADMIN only, and every one of them is
#: written to the audit log with the calling key's ID (7).
ADMIN_PATTERNS = (
    re.compile(r"^/api/memory/clear"),
    re.compile(r"^/api/history/clear"),
    re.compile(r"^/api/mock-data"),
    re.compile(r"^/api/settings$"),
    re.compile(r"^/api/models"),
)

#: Ingest and anything that triggers an LLM call. MANAGER or above.
MANAGER_PATTERNS = (
    re.compile(r"^/api/ingest/"),
    re.compile(r"^/api/run"),
    re.compile(r"^/api/score/"),
    re.compile(r"^/api/feedback"),
)

#: Webhook ingest authenticates by HMAC body signature instead of a bearer key,
#: because the sender is a system that cannot hold a rotating token.
HMAC_PATHS = frozenset({"/api/ingest/webhook"})


def is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith(PUBLIC_PREFIXES):
        return True
    return path.endswith(PUBLIC_SUFFIXES)


def uses_hmac(path: str) -> bool:
    return path in HMAC_PATHS


def required_role(method: str, path: str) -> Role:
    """The minimum role for this request.

    Note the ordering: admin patterns are checked before the safe-method
    shortcut, so `GET /api/models` is admin-gated too. Which models are running
    and how they were evaluated is operational detail, not something every
    viewer needs.
    """
    for pattern in ADMIN_PATTERNS:
        if pattern.match(path):
            return Role.ADMIN

    if method.upper() in SAFE_METHODS:
        return Role.VIEWER

    for pattern in MANAGER_PATTERNS:
        if pattern.match(path):
            return Role.MANAGER

    # Default-deny for anything mutating that nobody classified. A new POST
    # route is admin-only until somebody decides otherwise, in this file, on
    # purpose.
    return Role.ADMIN
