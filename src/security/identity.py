# src/security/identity.py
# Who is calling, and what are they allowed to do (spec 7, blocker B1).
#
# Choice made: SIGNED API KEYS, not OIDC.
#
# 7 says "OIDC login for humans, signed API keys or HMAC signatures for webhook
# ingest -- pick one and do it properly". OIDC is the better answer for a real
# deployment with real employees behind it, and it is the wrong thing to build
# first here: it needs an identity provider, a redirect flow, session handling
# and a frontend that does not exist yet (Phase 6). Half an OIDC integration
# protects nothing, and a route that is 401 for the wrong reason is no safer
# than one that is 200.
#
# API keys done properly is a complete control today: every mutating route
# rejects unauthenticated callers, every key carries a role, and every
# destructive action is attributable to a key ID in the audit log. The migration
# path is written down in docs/LIMITATIONS.md -- `Principal` is what the rest of
# the codebase depends on, and an OIDC exchange later just produces the same
# object from a token instead of from a header.
#
# What is stored is the SHA-256 of each key, never the key. An attacker who
# reads the configuration cannot then call the API with it.

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from enum import IntEnum

from pydantic import BaseModel, ConfigDict

from src.config import API_KEYS_ENV, WEBHOOK_SECRET_ENV, ConfigError, get_settings

logger = logging.getLogger(__name__)

#: Re-exported from src/config.py so the names are defined once. Both are
#: still importable from here, which is where callers have always looked.
__all__ = [
    "API_KEYS_ENV",
    "WEBHOOK_SECRET_ENV",
    "ApiKey",
    "KeyRing",
    "Principal",
    "Role",
    "hash_key",
    "verify_webhook_signature",
]


class Role(IntEnum):
    """Ordered so that comparison expresses privilege directly.

    An IntEnum rather than strings because every check in the codebase is
    "at least this much", and `role >= Role.MANAGER` cannot be got wrong the way
    a set-membership check against a hand-maintained list can.
    """

    VIEWER = 10
    MANAGER = 20
    ADMIN = 30


ROLE_NAMES = {
    "viewer": Role.VIEWER,
    "manager": Role.MANAGER,
    "admin": Role.ADMIN,
}


class Principal(BaseModel):
    """The authenticated caller.

    This is the object the rest of the system depends on. Swapping API keys for
    OIDC later means producing this from a validated token instead of from a
    header -- nothing downstream changes.
    """

    model_config = ConfigDict(frozen=True)

    key_id: str
    role: Role

    def can(self, required: Role) -> bool:
        return self.role >= required


class ApiKey(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    role: Role
    key_sha256: str


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_configured() -> list[ApiKey]:
    """Read keys from the validated configuration.

    A bad `API_KEYS` still yields NO keys here rather than an exception, and
    that has not changed: this is a library that middleware constructs, and the
    safe failure for it is "authenticate nobody", never "authenticate anyone".

    What changed is that a deployment does not reach this point at all. `app.py`
    validates the configuration at startup and refuses to serve on a malformed
    `API_KEYS` (src/config.py), so a typo is now a failure to boot with an
    explanation instead of a server that starts, prints a temporary key nobody
    is watching for, and rejects every real caller.
    """
    try:
        specs = get_settings().api_keys
    except ConfigError:
        logger.error(
            "%s is set but is not usable. NO KEYS LOADED -- every "
            "authenticated route will reject every caller.",
            API_KEYS_ENV,
        )
        return []

    return [
        ApiKey(id=spec.id, role=ROLE_NAMES[spec.role], key_sha256=spec.key_sha256)
        for spec in specs
    ]


class KeyRing:
    """The configured keys, and the check against them.

    When nothing is configured, one ephemeral admin key is generated and printed
    at startup. That is deliberately NOT an "auth disabled" mode: there is no
    code path in this system where a mutating route serves an unauthenticated
    caller. A bypass flag for local convenience is exactly the flag that ends up
    set in a deployment, and B1 is on the blocker list because that already
    happened here once.
    """

    def __init__(self, keys: list[ApiKey] | None = None) -> None:
        self._keys = keys if keys is not None else _parse_configured()
        self.generated_key: str | None = None

        if not self._keys:
            self.generated_key = secrets.token_urlsafe(32)
            self._keys = [
                ApiKey(
                    id="ephemeral-admin",
                    role=Role.ADMIN,
                    key_sha256=hash_key(self.generated_key),
                )
            ]

    @property
    def is_ephemeral(self) -> bool:
        """True when running on a generated key rather than configured ones."""
        return self.generated_key is not None

    def startup_banner(self) -> str:
        """What to print at boot. Loud, because a generated key is not production."""
        if not self.is_ephemeral:
            return f"Auth: {len(self._keys)} API key(s) loaded from {API_KEYS_ENV}."
        return (
            "\n"
            + "=" * 72
            + f"\n  No {API_KEYS_ENV} configured. Generated a TEMPORARY admin key:\n"
            + f"\n      {self.generated_key}\n"
            + "\n  It changes on every restart and is not suitable for anything"
            "\n  but local use. Send it as:  Authorization: Bearer <key>\n" + "=" * 72
        )

    def authenticate(self, presented: str | None) -> Principal | None:
        """Resolve a presented key to a principal, or None.

        Every candidate is compared even after a match is found, and the
        comparison is constant-time. A loop that returns early leaks which key
        prefix was correct through timing; it costs nothing to not do that.
        """
        if not presented:
            return None

        digest = hash_key(presented)
        matched: ApiKey | None = None
        for key in self._keys:
            if hmac.compare_digest(digest, key.key_sha256):
                matched = key

        if matched is None:
            return None
        return Principal(key_id=matched.id, role=matched.role)


def verify_webhook_signature(body: bytes, signature: str | None) -> bool:
    """Check an HMAC-SHA256 signature over the raw request body.

    Webhook senders cannot hold a rotating bearer token, so ingest is
    authenticated by signing the payload instead (7). Signing the BODY rather
    than issuing the sender a key also means a captured request cannot be
    replayed with different contents.

    Returns False when no secret is configured: an unsigned webhook is not
    trusted just because the server was not told what to expect.
    """
    secret = get_settings().webhook_signing_secret
    if not secret or not signature:
        return False

    provided = signature.strip()
    if provided.startswith("sha256="):
        provided = provided[len("sha256=") :]

    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided.lower())
