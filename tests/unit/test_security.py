# Phase 4 -- the security baseline (PRODUCTION_EVOLUTION_PROMPT.md 7).
#
# Exit criterion: "unauthenticated requests to mutating routes return 401,
# proven by a security test suite." This is that suite.
#
# The route list below is derived from the live application rather than
# hardcoded, so a route added next month is tested the moment it exists. A
# hand-maintained list of protected routes is exactly the failure that produced
# blocker B1 -- `POST /api/memory/clear` was not on anybody's list either.

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from src.governance.audit import record_access, verify_chain
from src.security.identity import (
    ApiKey,
    KeyRing,
    Principal,
    Role,
    hash_key,
    verify_webhook_signature,
)
from src.security.limits import (
    MAX_BODY_BYTES,
    IdempotencyStore,
    RateLimiter,
)
from src.security.middleware import SECURITY_HEADERS
from src.security.policy import is_public, required_role

ADMIN_KEY = "test-admin-key-do-not-use"
MANAGER_KEY = "test-manager-key-do-not-use"
VIEWER_KEY = "test-viewer-key-do-not-use"


@pytest.fixture(scope="module")
def client():
    """The real application, with a known key ring and every side effect stubbed.

    Two things are neutralised, and both matter:

    * the LLM path -- 6.3 says CI must never call a real LLM, and an
      authorisation test that spends API quota to prove a 403 is a bad trade;
    * the destructive routes -- this suite exercises `POST /api/memory/clear`
      by design, and it must not clear the developer's actual memory directory
      to do it. A security test that destroys real data to prove it is guarded
      has failed at the thing it is testing.
    """
    import app as app_module
    from src.security.middleware import SecurityMiddleware

    keyring = KeyRing(
        [
            ApiKey(id="admin", role=Role.ADMIN, key_sha256=hash_key(ADMIN_KEY)),
            ApiKey(id="manager", role=Role.MANAGER, key_sha256=hash_key(MANAGER_KEY)),
            ApiKey(id="viewer", role=Role.VIEWER, key_sha256=hash_key(VIEWER_KEY)),
        ]
    )

    # Replace the key ring on the already-installed middleware.
    for middleware in app_module.app.user_middleware:
        if middleware.cls is SecurityMiddleware:
            middleware.kwargs["keyring"] = keyring
    app_module.app.middleware_stack = app_module.app.build_middleware_stack()

    with TestClient(app_module.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch, tmp_path):
    """No network, no writes outside tmp_path, for every test in this module."""
    import app as app_module

    def _no_llm(*args, **kwargs):
        raise AssertionError("a security test attempted a live LLM call")

    for module_name in (
        "src.orchestrator_agent",
        "src.risk_scorer_agent",
        "src.trend_detector_agent",
        "src.manager_briefing_agent",
    ):
        import importlib

        module = importlib.import_module(module_name)
        if hasattr(module, "run_agent_sync"):
            monkeypatch.setattr(module, "run_agent_sync", _no_llm)

    # Patched where it is USED, not where it is defined. After the Phase 5
    # restructure `run_orchestrator` lives in the pipeline router; patching
    # `app` still "succeeded" silently with raising=False and left the rate-limit
    # test spawning real pipeline threads against real data.
    from src.api.routers import pipeline as pipeline_router

    monkeypatch.setattr(pipeline_router, "run_orchestrator", lambda *a, **k: "stubbed")

    # Point every writable directory at tmp_path. Patched on the modules that
    # read them, since they are imported by value at module load.
    from src.api import paths as api_paths
    from src.api.routers import employees, ingest, maintenance, simulator

    for module in (
        api_paths,
        pipeline_router,
        employees,
        ingest,
        maintenance,
        simulator,
        app_module,
    ):
        for name in (
            "MEMORY_DIR",
            "WEEKLY_DIR",
            "REALTIME_DIR",
            "REALTIME_MEMORY_DIR",
            "SIMULATOR_MEMORY_DIR",
        ):
            if hasattr(module, name):
                target = tmp_path / name.lower()
                target.mkdir(parents=True, exist_ok=True)
                monkeypatch.setattr(module, name, str(target))


def _mutating_routes(client) -> list[tuple[str, str]]:
    """Every non-safe route the live app exposes."""
    found = []
    for route in client.app.routes:
        methods = getattr(route, "methods", set()) or set()
        path = getattr(route, "path", "")
        if not path.startswith("/api/"):
            continue
        for method in methods:
            if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                found.append((method.upper(), path))
    assert found, "no mutating routes discovered -- the test is checking nothing"
    return sorted(set(found))


# ---------------------------------------------------------------------------
# The exit criterion
# ---------------------------------------------------------------------------
def test_every_mutating_route_rejects_an_unauthenticated_caller(client):
    """Blocker B1, closed and kept closed.

    Derived from the live route table, so a route added later is covered without
    anyone remembering to add it here.
    """
    failures = []
    for method, path in _mutating_routes(client):
        concrete = path.replace("{name}", "someone")
        response = client.request(method, concrete, json={})
        if response.status_code != 401:
            failures.append(f"{method} {concrete} -> {response.status_code}")

    assert not failures, (
        "these mutating routes did not require authentication:\n  "
        + "\n  ".join(failures)
    )


def test_reads_of_employee_data_also_require_authentication(client):
    """This system's READS are the sensitive operation -- the whole product is
    looking at people."""
    for path in (
        "/api/employees",
        "/api/history",
        "/api/report/raw",
        "/api/calibration",
        "/api/employee/someone/briefing",
    ):
        assert client.get(path).status_code == 401, path


def test_a_wrong_key_is_refused(client):
    response = client.post(
        "/api/memory/clear", headers={"Authorization": "Bearer not-a-real-key"}
    )
    assert response.status_code == 401


def test_the_error_does_not_describe_the_authorisation_model(client):
    """401 for both a missing and a wrong key, and no hint about roles or keys."""
    missing = client.post("/api/memory/clear")
    wrong = client.post("/api/memory/clear", headers={"Authorization": "Bearer nope"})

    assert missing.status_code == wrong.status_code == 401
    for response in (missing, wrong):
        body = response.text.lower()
        for leak in ("admin", "manager", "viewer", "role", "key_id", "sha256"):
            assert leak not in body, f"401 body leaked {leak!r}"


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
def test_a_viewer_cannot_destroy_data(client):
    response = client.post(
        "/api/memory/clear", headers={"Authorization": f"Bearer {VIEWER_KEY}"}
    )
    assert response.status_code == 403


def test_a_manager_cannot_destroy_data_either(client):
    """Destructive routes are admin-only (§7), not merely authenticated."""
    response = client.post(
        "/api/memory/clear", headers={"Authorization": f"Bearer {MANAGER_KEY}"}
    )
    assert response.status_code == 403


def test_a_viewer_can_read(client):
    response = client.get(
        "/api/history", headers={"Authorization": f"Bearer {VIEWER_KEY}"}
    )
    assert response.status_code == 200


def test_an_admin_is_not_blocked_by_authorisation(client):
    """Uses an admin-gated route with no side effects, so proving the positive
    case does not require destroying anything."""
    response = client.get(
        "/api/models", headers={"Authorization": f"Bearer {ADMIN_KEY}"}
    )
    assert response.status_code == 200


def test_health_probes_stay_public(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_security_headers_are_present_on_every_response(client):
    for response in (client.get("/healthz"), client.get("/api/history")):
        for header in SECURITY_HEADERS:
            assert header in response.headers, header
    assert (
        "frame-ancestors 'none'"
        in client.get("/healthz").headers["Content-Security-Policy"]
    )


# ---------------------------------------------------------------------------
# The policy table
# ---------------------------------------------------------------------------
def test_an_unclassified_mutating_route_defaults_to_admin():
    """Default-deny. A new POST route is admin-only until somebody decides
    otherwise, in policy.py, on purpose."""
    assert required_role("POST", "/api/something-invented-next-year") is Role.ADMIN
    assert required_role("DELETE", "/api/whatever") is Role.ADMIN


def test_destructive_routes_are_admin_even_for_reads():
    assert required_role("GET", "/api/models") is Role.ADMIN
    assert required_role("POST", "/api/memory/clear") is Role.ADMIN
    assert required_role("POST", "/api/history/clear") is Role.ADMIN
    assert required_role("POST", "/api/mock-data") is Role.ADMIN


def test_ingest_and_llm_routes_require_a_manager():
    assert required_role("POST", "/api/ingest/upload") is Role.MANAGER
    assert required_role("POST", "/api/run") is Role.MANAGER
    assert required_role("POST", "/api/feedback") is Role.MANAGER


def test_a_version_prefix_never_changes_a_permission():
    """Regression: mounting the routers at /api/v1 silently downgraded
    `GET /api/v1/models` from ADMIN to VIEWER, because the policy patterns
    simply stopped matching and the route fell through to the safe-method
    default.

    That is the B1 failure shape in miniature -- nothing decided the route
    should be less protected, a path just stopped matching a list. This checks
    every route the app exposes, under every version prefix, so a future
    /api/v2 cannot reintroduce it.
    """
    paths = [
        "/api/models",
        "/api/memory/clear",
        "/api/history/clear",
        "/api/mock-data",
        "/api/settings",
        "/api/feedback",
        "/api/interventions",
        "/api/interventions/outcomes",
        "/api/calibration",
        "/api/ingest/upload",
        "/api/ingest/webhook",
        "/api/run",
        "/api/employees",
        "/api/something-new",
    ]
    for path in paths:
        for method in ("GET", "POST", "DELETE"):
            unversioned = required_role(method, path)
            for version in ("v1", "v2", "v17"):
                versioned = required_role(
                    method, path.replace("/api", f"/api/{version}", 1)
                )
                assert versioned is unversioned, (
                    f"{method} {path} is {unversioned.name} unversioned but "
                    f"{versioned.name} under /{version}"
                )


def test_hmac_routing_survives_the_version_prefix():
    from src.security.policy import uses_hmac

    assert uses_hmac("/api/ingest/webhook") is True
    assert uses_hmac("/api/v1/ingest/webhook") is True
    assert uses_hmac("/api/v1/ingest/upload") is False


def test_the_public_surface_is_tiny():
    assert is_public("/") is True
    assert is_public("/healthz") is True
    assert is_public("/index.html") is True
    assert is_public("/static/app.js") is True

    for path in (
        "/api/employees",
        "/api/memory/clear",
        "/api/history",
        "/api/calibration",
    ):
        assert is_public(path) is False, path


# ---------------------------------------------------------------------------
# Key handling
# ---------------------------------------------------------------------------
def test_keys_are_stored_only_as_hashes():
    ring = KeyRing([ApiKey(id="a", role=Role.ADMIN, key_sha256=hash_key("secret"))])
    assert ring.authenticate("secret") is not None
    assert ring.authenticate("Secret") is None

    serialised = json.dumps([k.model_dump() for k in ring._keys])
    assert "secret" not in serialised


def test_no_configured_keys_means_a_generated_key_not_an_open_door():
    """There is no 'auth disabled' mode. A bypass flag for local convenience is
    exactly the flag that ends up set in a deployment."""
    ring = KeyRing([])
    assert ring.is_ephemeral is True
    assert ring.generated_key
    assert ring.authenticate(None) is None
    assert ring.authenticate("") is None
    assert ring.authenticate("guess") is None
    assert ring.authenticate(ring.generated_key) is not None
    assert "TEMPORARY" in ring.startup_banner()


def test_roles_compare_by_privilege():
    admin = Principal(key_id="a", role=Role.ADMIN)
    viewer = Principal(key_id="v", role=Role.VIEWER)

    assert admin.can(Role.VIEWER) and admin.can(Role.ADMIN)
    assert viewer.can(Role.VIEWER)
    assert not viewer.can(Role.MANAGER)
    assert not viewer.can(Role.ADMIN)


def test_malformed_key_configuration_loads_nothing_rather_than_guessing(monkeypatch):
    monkeypatch.setenv("API_KEYS", "{not json")
    ring = KeyRing()
    assert ring.is_ephemeral is True  # fell back to a generated key, not to open

    monkeypatch.setenv("API_KEYS", json.dumps([{"id": "x", "role": "wizard"}]))
    assert KeyRing().is_ephemeral is True


def test_valid_key_configuration_is_loaded(monkeypatch):
    monkeypatch.setenv(
        "API_KEYS",
        json.dumps([{"id": "ci", "role": "admin", "key_sha256": hash_key("k")}]),
    )
    ring = KeyRing()
    assert ring.is_ephemeral is False
    principal = ring.authenticate("k")
    assert principal is not None and principal.role is Role.ADMIN


# ---------------------------------------------------------------------------
# Webhook signatures
# ---------------------------------------------------------------------------
def test_webhook_signature_is_verified_over_the_body(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", "shared-secret-not-a-real-one")
    body = b'{"employee_name": "Ade", "week": 1}'
    signature = hmac.new(
        b"shared-secret-not-a-real-one", body, hashlib.sha256
    ).hexdigest()

    assert verify_webhook_signature(body, signature) is True
    assert verify_webhook_signature(body, f"sha256={signature}") is True

    # A captured request cannot be replayed with different contents.
    assert (
        verify_webhook_signature(b'{"employee_name": "Someone else"}', signature)
        is False
    )
    assert verify_webhook_signature(body, "deadbeef") is False
    assert verify_webhook_signature(body, None) is False


def test_an_unsigned_webhook_is_not_trusted_by_default(monkeypatch):
    """No configured secret means no trust -- not blanket acceptance."""
    monkeypatch.delenv("WEBHOOK_SIGNING_SECRET", raising=False)
    assert verify_webhook_signature(b"{}", "anything") is False


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def test_rate_limiter_allows_a_budget_then_refuses():
    limiter = RateLimiter(limit=3, window=60)
    for _ in range(3):
        allowed, _ = limiter.check("caller")
        assert allowed is True

    allowed, retry_after = limiter.check("caller")
    assert allowed is False
    assert retry_after >= 1


def test_rate_limits_are_per_identity():
    limiter = RateLimiter(limit=1, window=60)
    assert limiter.check("a")[0] is True
    assert limiter.check("b")[0] is True, "one caller's budget consumed another's"
    assert limiter.check("a")[0] is False


def test_the_window_slides_rather_than_resetting_on_a_boundary():
    """A fixed window lets a caller send a full budget at 11:59:59 and another
    at 12:00:00 -- double the intended rate against the routes that cost money."""
    limiter = RateLimiter(limit=2, window=10)
    assert limiter.check("a", now=0.0)[0] is True
    assert limiter.check("a", now=1.0)[0] is True
    assert limiter.check("a", now=5.0)[0] is False
    # The first hit ages out at t=10; the second at t=11.
    assert limiter.check("a", now=10.5)[0] is True
    assert limiter.check("a", now=10.6)[0] is False


def test_expensive_routes_are_rate_limited_in_the_app(client):
    from src.security.limits import EXPENSIVE_LIMIT

    headers = {"Authorization": f"Bearer {MANAGER_KEY}"}
    statuses = [
        client.post("/api/run", headers=headers).status_code
        for _ in range(EXPENSIVE_LIMIT + 3)
    ]
    assert 429 in statuses, "an LLM-triggering route was not rate limited"


# ---------------------------------------------------------------------------
# Body size and idempotency
# ---------------------------------------------------------------------------
def test_an_oversized_body_is_refused_before_it_is_read(client):
    response = client.post(
        "/api/ingest/raw",
        headers={
            "Authorization": f"Bearer {MANAGER_KEY}",
            "Content-Length": str(MAX_BODY_BYTES + 1),
        },
        content=b"x",
    )
    assert response.status_code == 413


def test_idempotency_store_recognises_a_retry():
    store = IdempotencyStore()
    assert store.seen("key-1") is None

    store.remember("key-1", {"status": "ingested", "rows": 4})
    assert store.seen("key-1") == {"status": "ingested", "rows": 4}
    assert store.seen("key-2") is None


def test_idempotency_store_is_bounded():
    """An attacker sending unique keys must not grow this without limit."""
    from src.security.limits import MAX_IDEMPOTENCY_KEYS

    store = IdempotencyStore()
    for i in range(MAX_IDEMPOTENCY_KEYS + 200):
        store.remember(f"key-{i}", {"i": i})

    assert len(store._seen) <= MAX_IDEMPOTENCY_KEYS


# ---------------------------------------------------------------------------
# Audit hash chain
# ---------------------------------------------------------------------------
def test_the_audit_chain_verifies_when_untouched(tmp_path):
    db = str(tmp_path / "audit.db")
    for i in range(5):
        record_access(
            actor="admin", action=f"action-{i}", purpose="testing", db_path=db
        )

    intact, broken_at = verify_chain(db)
    assert intact is True
    assert broken_at is None


def test_editing_an_audit_row_is_detectable(tmp_path):
    """Append-only triggers protect the log from code using this module. Anyone
    with the file can still rewrite it -- the chain is what makes that visible."""
    import sqlite3

    db = str(tmp_path / "audit.db")
    for i in range(5):
        record_access(
            actor="admin", action=f"action-{i}", purpose="testing", db_path=db
        )

    conn = sqlite3.connect(db)
    conn.execute("DROP TRIGGER access_log_no_update")
    conn.execute("UPDATE access_log SET actor = 'somebody-else' WHERE id = 3")
    conn.commit()
    conn.close()

    intact, broken_at = verify_chain(db)
    assert intact is False
    assert broken_at == 3


def test_deleting_an_audit_row_is_detectable(tmp_path):
    import sqlite3

    db = str(tmp_path / "audit.db")
    for i in range(5):
        record_access(
            actor="admin", action=f"action-{i}", purpose="testing", db_path=db
        )

    conn = sqlite3.connect(db)
    conn.execute("DROP TRIGGER access_log_no_delete")
    conn.execute("DELETE FROM access_log WHERE id = 3")
    conn.commit()
    conn.close()

    intact, broken_at = verify_chain(db)
    assert intact is False
    assert broken_at == 4


def test_an_audit_log_created_before_hash_chaining_still_accepts_writes(tmp_path):
    """Regression: `CREATE TABLE IF NOT EXISTS` does nothing to an existing
    table, so a pre-Phase-4 audit.db kept its old shape and every write failed
    on the missing column -- silently, because record_access() swallows
    exceptions by design. The log simply stopped recording.

    Found by running the application, not by a test: the tests all used fresh
    temporary databases and never met an old one.
    """
    import sqlite3

    from src.governance import audit

    db = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
            subject_id TEXT, purpose TEXT NOT NULL, resource TEXT,
            outcome TEXT NOT NULL, detail TEXT
        );
        INSERT INTO access_log (ts, actor, action, purpose, outcome)
        VALUES ('2026-01-01T00:00:00Z', 'legacy', 'GET /old', 'testing', 'allowed');
        """
    )
    conn.commit()
    conn.close()

    audit._initialised.discard(db)
    record_access(actor="admin", action="GET /new", purpose="testing", db_path=db)

    entries = audit.query_access(db_path=db)
    assert len(entries) == 2, "the write silently failed against a legacy log"
    assert entries[0]["entry_hash"], "the new entry was written without a hash"

    # Pre-chain rows are unverifiable, not tampering.
    intact, broken_at = verify_chain(db)
    assert intact is True
    assert broken_at is None


def test_removing_a_hash_after_the_chain_starts_is_tampering(tmp_path):
    """A NULL hash is only innocent BEFORE the chain begins. After that it is
    somebody deleting one."""
    import sqlite3

    db = str(tmp_path / "audit.db")
    for i in range(4):
        record_access(actor="admin", action=f"a-{i}", purpose="testing", db_path=db)

    conn = sqlite3.connect(db)
    conn.execute("DROP TRIGGER access_log_no_update")
    conn.execute("UPDATE access_log SET entry_hash = NULL WHERE id = 3")
    conn.commit()
    conn.close()

    intact, broken_at = verify_chain(db)
    assert intact is False
    assert broken_at == 3


def test_a_refused_request_is_written_to_the_audit_log(client, tmp_path, monkeypatch):
    """Denials are the entries that matter most: a pattern of refusals is the
    only early signal that somebody is trying doors."""
    from src.governance import audit

    db = str(tmp_path / "audit.db")
    monkeypatch.setenv("AUDIT_DB_PATH", db)

    client.post("/api/memory/clear")

    entries = audit.query_access(db_path=db)
    assert any(e["outcome"] == "denied" for e in entries), (
        "an unauthenticated attempt on a destructive route left no audit trail"
    )


def test_every_refusal_is_an_rfc9457_problem_document(client):
    """The errors a caller is most likely to meet must not be the only ones with
    a different shape.

    Middleware runs before the exception handlers, so 401/403/413/429 build
    their own problem documents. When they returned plain `{"detail": ...}` the
    frontend client -- which reads `title` -- silently fell back to a generic
    message on every auth failure.
    """
    responses = {
        401: client.get("/api/employees"),
        403: client.post(
            "/api/memory/clear", headers={"Authorization": f"Bearer {VIEWER_KEY}"}
        ),
    }
    for expected_status, response in responses.items():
        assert response.status_code == expected_status
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["status"] == expected_status
        assert body["title"]
        assert body["type"].startswith("https://")


def test_versioned_and_unversioned_paths_agree_on_the_live_app(client):
    """Same resource, same answer, whichever prefix is used."""
    for path in ("/api/models", "/api/v1/models"):
        anonymous = client.get(path)
        viewer = client.get(path, headers={"Authorization": f"Bearer {VIEWER_KEY}"})
        admin = client.get(path, headers={"Authorization": f"Bearer {ADMIN_KEY}"})
        assert anonymous.status_code == 401, path
        assert viewer.status_code == 403, path
        assert admin.status_code == 200, path


def test_reads_get_a_budget_that_ordinary_use_does_not_exhaust(client):
    """A single operator loading a few pages must not trip the limiter.

    One 30-per-minute bucket for everything looked prudent and broke the
    dashboard: three or four calls per page, plus run-progress polling, exceeded
    it in normal use. A read limit low enough to break the product does not buy
    security -- it buys a tool people work around.
    """
    from src.security.limits import DEFAULT_LIMIT, READ_LIMIT

    assert READ_LIMIT > DEFAULT_LIMIT * 5

    headers = {"Authorization": f"Bearer {VIEWER_KEY}"}
    statuses = {
        client.get("/api/history", headers=headers).status_code for _ in range(60)
    }
    assert 429 not in statuses, "sixty reads tripped the limiter"


def test_llm_triggering_routes_keep_a_tight_budget():
    """The limit that protects the API quota is unchanged and stays small."""
    from src.security.limits import EXPENSIVE_LIMIT, READ_LIMIT

    assert EXPENSIVE_LIMIT <= 10
    assert EXPENSIVE_LIMIT < READ_LIMIT


def test_every_ingest_route_honours_an_idempotency_key(client):
    """A sender that times out and retries must not append a second copy.

    Nobody sees an error when it does: one person's metrics silently double,
    which reads as an employee whose output suddenly improved. Derived from the
    live route table, so an ingest path added later is covered without anyone
    remembering.
    """
    import inspect

    from src.api.routers import ingest as ingest_router

    ingest_posts = [
        route
        for route in client.app.routes
        if getattr(route, "path", "").startswith("/api/v1/ingest/")
        and "POST" in (getattr(route, "methods", set()) or set())
    ]
    assert ingest_posts, "no ingest routes discovered"

    missing = []
    for route in ingest_posts:
        source = inspect.getsource(route.endpoint)
        if "_replay(request)" not in source:
            missing.append(route.path)

    assert not missing, (
        "these ingest routes do not honour Idempotency-Key, so a retry "
        f"duplicates a week: {missing}"
    )
    assert hasattr(ingest_router, "idempotency")
