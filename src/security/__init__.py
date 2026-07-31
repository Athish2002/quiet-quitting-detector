# src/security/ -- authentication, authorisation and abuse limits (spec 7).
#
# Closes blocker B1 ("zero authentication / authorization; every route is
# public; POST /api/memory/clear wipes all data unauthenticated").
#
# The organising decision is DEFAULT-DENY, in the same shape as
# config/data_allowlist.json: `policy.py` states what is public and what each
# route needs, and `middleware.py` applies it to every request including routes
# that do not exist yet. Nothing here is opt-in per route, because the route
# somebody forgets to opt in is exactly the one B1 describes.

from src.security.identity import (
    ApiKey,
    KeyRing,
    Principal,
    Role,
    hash_key,
    verify_webhook_signature,
)
from src.security.limits import IdempotencyStore, RateLimiter
from src.security.middleware import SECURITY_HEADERS, SecurityMiddleware
from src.security.policy import is_public, required_role

__all__ = [
    "SECURITY_HEADERS",
    "ApiKey",
    "IdempotencyStore",
    "KeyRing",
    "Principal",
    "RateLimiter",
    "Role",
    "SecurityMiddleware",
    "hash_key",
    "is_public",
    "required_role",
    "verify_webhook_signature",
]
