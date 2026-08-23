# app.py -- composition root.
#
# Phase 5 (PRODUCTION_EVOLUTION_PROMPT.md §9) closes blocker B4: this was a
# 1,400-line module holding 30+ routes, mock-data generation, CSV parsing and
# LLM calls, and nothing in it could be tested without a request object.
#
# What is left here is assembly and nothing else: build the app, install
# middleware and error handlers, mount routers, serve the static bundle. Every
# handler lives in `src/api/routers/`, and every one of those is thin -- validate,
# call into `domain` or `evolution`, shape a response.
#
# Ordering below is load-bearing and easy to get wrong:
#   * `.env` must load before any import that reads configuration at import
#     time, or the server starts with no API keys and every provider silently
#     drops to a local fallback tier;
#   * middleware runs in reverse registration order, so the security middleware
#     is added LAST and executes FIRST -- an unauthenticated request is refused
#     before any route or any other middleware sees it;
#   * the static mount is last because it claims "/".

import logging
import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.api import errors as api_errors
from src.api.routers import (
    employees,
    evolution,
    ingest,
    ingest_sources,
    maintenance,
    pipeline,
    reports,
    simulator,
    system,
)
from src.config import get_settings
from src.security import KeyRing, SecurityMiddleware

logger = logging.getLogger(__name__)

# --- Configuration ----------------------------------------------------------
# Read and validated BEFORE anything is assembled, so a bad value is a refusal
# to start with an explanation rather than a server that comes up looking fine.
# The failure this prevents is specific: a malformed API_KEYS used to be
# absorbed -- the key ring loaded nothing, printed a temporary key into a log
# nobody was watching, and then rejected every real caller. That is a
# five-hour outage that looks like a client problem.
#
# `ConfigError` is deliberately not caught. Uvicorn exits non-zero, the
# container fails its healthcheck, and the orchestrator does not roll the
# release forward.
settings = get_settings()
logger.warning(settings.startup_summary())

app = FastAPI(
    title="Quiet-Quitting Detector",
    description=(
        "Multi-agent employee disengagement detection. Every employee is "
        "evaluated against their own baseline, never a cohort average, and "
        "briefings are supportive by construction."
    ),
    version="1.0.0",
)

# --- CORS -------------------------------------------------------------------
# An explicit allowlist, never "*". With credentials enabled a wildcard would
# let any origin drive an authenticated session.
# The "never *" part is now enforced rather than described: `Settings` refuses
# a wildcard outright, so this comment cannot quietly become untrue.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allow_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    """Nothing here is cacheable: every response is data about a person."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# --- Security (§7, blocker B1) ----------------------------------------------
# Added last so it runs first. Default-deny middleware rather than per-route
# dependencies: a decorator protects the routes somebody remembered to decorate,
# and B1 exists because `POST /api/memory/clear` was not one of them.
_keyring = KeyRing()
app.add_middleware(SecurityMiddleware, keyring=_keyring)
logger.warning(_keyring.startup_banner())

# RFC 9457 problem+json, and the last line of defence for CONTEXT.md rule 4: an
# unhandled exception returns an opaque message plus a correlation ID, never a
# stack trace. Traces here contain employee names.
api_errors.install(app)


# --- Routers ----------------------------------------------------------------
# Mounted twice on purpose. `/api/v1` is the versioned contract the generated
# frontend client targets; the bare `/api` alias keeps existing callers working
# and is hidden from the schema so the client only ever sees one canonical path.
# `src/security/policy.py` normalises the version segment, so both forms resolve
# to identical permissions.
_ROUTERS = (
    system.router,
    pipeline.router,
    employees.router,
    reports.router,
    maintenance.router,
    ingest.router,
    ingest_sources.router,
    simulator.router,
    evolution.router,
)

for router in _ROUTERS:
    app.include_router(router, prefix="/api/v1")
    app.include_router(router, prefix="/api", include_in_schema=False)

# Liveness and favicon sit outside /api: they are the only routes that are
# public, and they say nothing about anybody.
app.include_router(system.probes)


@app.get("/readyz", include_in_schema=False)
def readyz() -> dict:
    """Readiness. Reports whether auth is running on a generated key."""
    return {
        "status": "ok",
        "auth": "ephemeral-key" if _keyring.is_ephemeral else "configured",
    }


# --- Static bundle ----------------------------------------------------------
# The built React SPA. The legacy 2,499-line `static/index.html` was retired in
# Phase 6: all four of its pages are migrated, and it had been non-functional
# since Phase 4 anyway -- it sent no API key, so every request it made returned
# 401. Its removal is what let the CSP drop 'unsafe-inline'.
#
# `frontend/dist` is a build artefact and is gitignored, so a fresh clone has no
# UI until `npm --prefix frontend run build` has run. That is normal for an SPA
# and the fallback below says so rather than serving a blank page.
SPA_DIST = os.path.join("frontend", "dist")

if os.path.exists(SPA_DIST):
    # Hashed bundles are served directly; everything else falls back to the
    # shell. The SPA uses history routing, so `/console` is an address the
    # browser can be pointed at but is not a file -- without the fallback every
    # deep link and every refresh 404s (and, behind the security middleware,
    # 401s, since a document request carries no Authorization header).
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(SPA_DIST, "assets")),
        name="assets",
    )

    _INDEX = os.path.join(SPA_DIST, "index.html")

    @app.get("/{spa_path:path}", include_in_schema=False)
    def spa_shell(spa_path: str) -> FileResponse:
        """Serve the app shell for any client-side route.

        Registered last, so every API router has already claimed its paths. A
        request for an unknown /api path still reaches FastAPI's own 404 because
        the routers are matched first.
        """
        # Containment check: `spa_path` comes from the URL, so a `../` would
        # otherwise read outside the bundle.
        root = os.path.abspath(SPA_DIST)
        candidate = os.path.abspath(os.path.join(root, spa_path))
        if (
            spa_path
            and (candidate == root or candidate.startswith(root + os.sep))
            and os.path.isfile(candidate)
        ):
            return FileResponse(candidate)
        return FileResponse(_INDEX)

else:

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index_fallback() -> str:
        return (
            "<html><body style='font-family:system-ui;text-align:center;"
            "padding-top:100px'><h1>Quiet-Quitting Detector</h1>"
            "<p>The API is running. Build the interface with "
            "<code>npm --prefix frontend run build</code>, or run "
            "<code>npm --prefix frontend run dev</code> for development.</p>"
            "</body></html>"
        )

# Reclaim temporary import memory immediately after assembly
import gc
gc.collect()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
