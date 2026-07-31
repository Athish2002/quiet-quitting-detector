# src/api/errors.py
# RFC 9457 problem+json error responses (PRODUCTION_EVOLUTION_PROMPT.md Phase 5).
#
# Two reasons this is worth doing properly rather than returning {"detail": ...}.
#
# The generated frontend client (Phase 6) needs one error SHAPE it can type. If
# some routes return `detail`, some return `message`, and some return a bare
# string, every call site grows its own error handling and the "a backend change
# that breaks the frontend must fail tsc" property is lost.
#
# And CONTEXT.md rule 4 -- never surface raw provider errors to users -- needs a
# place to be enforced rather than remembered. `problem()` takes a safe title
# and a correlation ID; the underlying exception goes to the log and never to
# the response. A stack trace reaching a manager's browser would be an ordinary
# bug in most products and a privacy incident in this one, because these traces
# contain employee names.

from __future__ import annotations

import logging
import uuid

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"

#: Stable, documented problem types. URIs are informational -- RFC 9457 does not
#: require them to resolve -- but they give the frontend something to switch on
#: that will not change when a human-readable title is reworded.
BASE_TYPE = "https://quiet-quitting-detector.invalid/problems"

TYPES = {
    400: f"{BASE_TYPE}/invalid-request",
    401: f"{BASE_TYPE}/authentication-required",
    403: f"{BASE_TYPE}/insufficient-permissions",
    404: f"{BASE_TYPE}/not-found",
    409: f"{BASE_TYPE}/conflict",
    413: f"{BASE_TYPE}/payload-too-large",
    422: f"{BASE_TYPE}/validation-failed",
    429: f"{BASE_TYPE}/rate-limited",
    500: f"{BASE_TYPE}/internal-error",
}

#: What a user is told when something unexpected breaks. Deliberately says
#: nothing about what broke.
SAFE_INTERNAL_TITLE = "The request could not be completed."


def problem(
    status: int,
    title: str,
    *,
    detail: str | None = None,
    correlation_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build an RFC 9457 problem document.

    `detail` must already be safe to show a user. Anything derived from an
    exception belongs in the log, keyed by the correlation ID, not here.
    """
    body = {
        "type": TYPES.get(status, TYPES[500]),
        "title": title,
        "status": status,
    }
    if detail:
        body["detail"] = detail
    if correlation_id:
        body["correlation_id"] = correlation_id

    return JSONResponse(
        status_code=status,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Render FastAPI's own HTTPExceptions as problem documents."""
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem(
        exc.status_code,
        _title_for(exc.status_code, detail),
        detail=detail,
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422s, with the offending fields but not their values.

    Echoing the submitted value back would put employee data into an error body
    that gets logged by proxies and pasted into bug reports.
    """
    fields = sorted(
        {
            ".".join(str(part) for part in error.get("loc", ())[1:])
            for error in exc.errors()
        }
    )
    return problem(
        422,
        "The request did not match the expected shape.",
        detail=f"Invalid or missing field(s): {', '.join(f for f in fields if f)}",
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """The last line of defence for CONTEXT.md rule 4.

    The real error is logged with a correlation ID; the caller gets an opaque
    message and that ID. Someone reporting "it broke, id 3f2a..." can be helped
    without a stack trace containing employee names ever leaving the server.
    """
    correlation_id = uuid.uuid4().hex[:12]
    logger.error(
        "Unhandled error [%s] on %s %s",
        correlation_id,
        request.method,
        request.url.path,
        exc_info=True,
    )
    return problem(
        500,
        SAFE_INTERNAL_TITLE,
        detail="Quote the correlation ID if you report this.",
        correlation_id=correlation_id,
    )


def _title_for(status: int, detail: str | None) -> str:
    if status == 401:
        return "Authentication required."
    if status == 403:
        return "Insufficient permissions."
    if status == 404:
        return "Not found."
    if status == 429:
        return "Rate limit exceeded."
    if status == 413:
        return "Request body too large."
    if status >= 500:
        return SAFE_INTERNAL_TITLE
    return detail or "The request could not be completed."


def install(app) -> None:
    """Register the handlers. Called from the composition root."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
