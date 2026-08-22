# Phase 5 exit criterion, enforced (PRODUCTION_EVOLUTION_PROMPT.md §9):
# "no file over 400 lines; app.py is composition root only."
#
# A line limit is a crude proxy and it is the right one here. Blocker B4 was not
# "app.py is long", it was that routes, orchestration, mock-data generation, CSV
# parsing and LLM calls lived in one module where none of them could be tested
# without a request object. Length is what that looks like from the outside, and
# it is the measure that cannot be argued with in review.
#
# KNOWN_OVERSIZED is deliberately a list with reasons rather than a blanket
# exemption, and it may only ever shrink -- the test below fails if a file on it
# grows. An exception list that is allowed to grow is not a gate.

import ast
import pathlib

MAX_LINES = 400

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Files that predate the restructure and are still over the limit, with the
#: line count at the moment they were recorded. Each is a separate piece of
#: work; splitting them under time pressure alongside a 30-route migration is
#: how a scorer quietly changes behaviour.
KNOWN_OVERSIZED = {
    # Monkey-patches the GenAI client constructor to inject keys (blocker B9),
    # plus the whole provider fallback chain. Wants the patching separated from
    # the chain before it is split.
    "src/app_utils/runner_helper.py": 500,
    # The LLM prompt, the provider fallback chain, the nearest-neighbour matcher
    # and the local-ML predictor. The fallback tiers want their own module.
    "src/risk_scorer_agent.py": 620,
    # CLI presentation: banners, table formatting, the chronological replay.
    # Wants a src/cli/ package with the rendering split from the driving.
    "run_pipeline.py": 560,
}


def _tracked_python_files() -> list[pathlib.Path]:
    files = []
    for path in ROOT.rglob("*.py"):
        parts = path.relative_to(ROOT).parts
        if any(
            part in {".venv", "node_modules", "__pycache__", "build", "dist"}
            for part in parts
        ):
            continue
        if parts[0] == "tests":
            continue  # test files are allowed to be long; they are not shipped
        files.append(path)
    assert files, "no source files discovered -- this test is checking nothing"
    return files


def test_no_source_file_exceeds_the_line_limit():
    violations = []
    for path in _tracked_python_files():
        relative = path.relative_to(ROOT).as_posix()
        lines = len(path.read_text(encoding="utf-8").splitlines())

        allowed = KNOWN_OVERSIZED.get(relative, MAX_LINES)
        if lines > allowed:
            violations.append(f"{relative}: {lines} lines (limit {allowed})")

    assert not violations, (
        "these files are over the limit. Split them rather than raising the "
        "limit:\n  " + "\n  ".join(violations)
    )


def test_the_oversized_list_only_ever_shrinks():
    """A file on the exception list must not grow toward its allowance.

    Without this the list becomes a place to park debt: a file at 612 lines with
    a 620 allowance quietly becomes 619, and the exception outlives the reason
    for it.
    """
    for relative, allowance in KNOWN_OVERSIZED.items():
        path = ROOT / relative
        if not path.exists():
            continue  # file was removed or split -- the good outcome
        lines = len(path.read_text(encoding="utf-8").splitlines())
        assert lines <= allowance, (
            f"{relative} grew to {lines} lines against an allowance of "
            f"{allowance}. Split it instead of raising the allowance."
        )


def test_app_py_is_a_composition_root():
    """No route handlers, no business logic -- assembly only.

    `app.py` may define at most a couple of trivial endpoints (the readiness
    probe and the no-static fallback). Anything more means a handler was added
    here instead of to a router, which is how the monolith came back last time.
    """
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    decorated = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(
            isinstance(d, ast.Call)
            and getattr(d.func, "attr", "")
            in {"get", "post", "put", "patch", "delete", "middleware"}
            for d in node.decorator_list
        )
    ]

    # Named rather than counted: a count lets a real handler slip in as long as
    # something else is removed. Each of these is assembly -- headers, a probe,
    # and the SPA shell -- with no domain logic in it.
    ALLOWED = {
        "add_no_cache_headers",
        "readyz",
        "spa_shell",
        "index_fallback",
    }
    unexpected = sorted(set(decorated) - ALLOWED)
    assert not unexpected, (
        "app.py has grown route handlers again -- these belong in "
        f"src/api/routers/: {unexpected}"
    )


def test_every_router_is_mounted():
    """A router nobody mounts is a set of endpoints that silently do not exist,
    and the security tests derive their route list from the live app -- so an
    unmounted router would also be an untested one."""
    import app as app_module

    router_modules = {
        path.stem
        for path in (ROOT / "src" / "api" / "routers").glob("*.py")
        if not path.stem.startswith("_") and path.stem != "nl_agent"
    }

    mounted_paths = set()

    def _collect_paths(routes, prefix=""):
        for r in routes:
            cur_prefix = prefix
            if hasattr(r, "include_context") and getattr(r.include_context, "prefix", None):
                cur_prefix += r.include_context.prefix
            if hasattr(r, "original_router") and hasattr(r.original_router, "routes"):
                _collect_paths(r.original_router.routes, cur_prefix)
            elif hasattr(r, "routes"):
                _collect_paths(r.routes, cur_prefix)
            else:
                p = cur_prefix + getattr(r, "path", "")
                if p:
                    mounted_paths.add(p)

    _collect_paths(app_module.app.routes)
    assert any(p.startswith("/api/v1") for p in mounted_paths), "nothing mounted"

    source = (ROOT / "app.py").read_text(encoding="utf-8")
    missing = [name for name in router_modules if name not in source]
    assert not missing, f"router modules exist but are never mounted: {missing}"


def test_nothing_outside_the_api_prefix_serves_data():
    """`is_public()` treats every non-/api path as the SPA shell, so a route
    added outside /api would be served to anonymous callers.

    That is safe only while the sole thing outside /api is the static bundle and
    the probes. If a data route ever appears there it must be caught here rather
    than discovered by someone reading employee records without a key.
    """
    import app as app_module
    from src.security.policy import API_PREFIX

    ALLOWED_NON_API = {
        "/",
        "/healthz",
        "/readyz",
        "/favicon.ico",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/docs/oauth2-redirect",
        "/{spa_path:path}",
        "/assets",
        "/assets/{path:path}",
    }

    offenders = [
        path
        for route in app_module.app.routes
        if (path := getattr(route, "path", ""))
        and not path.startswith(API_PREFIX)
        and path not in ALLOWED_NON_API
    ]
    assert not offenders, (
        "these routes sit outside /api and are therefore served without "
        f"authentication: {offenders}"
    )


def test_no_stateful_store_is_tracked_by_git():
    """Runtime databases must never be committed.

    `data/feedback.db` was tracked by accident: a `git add -A` caught it before
    the ignore rule existed, and .gitignore does NOT apply to files git is
    already tracking -- so the rule looked right and did nothing. It was empty
    and never reached the remote, but the next `git add -A` after a manager
    submitted a verdict would have published real feedback about real people to
    a public repository.

    Checked against git rather than the filesystem, because being ignored and
    being untracked are different things and only the second one protects
    anybody.
    """
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    ).stdout.splitlines()

    forbidden_suffixes = (".db", ".db-journal", ".sqlite", ".sqlite3")
    offenders = [
        path
        for path in tracked
        if path.endswith(forbidden_suffixes) or path.startswith("data/models/")
    ]

    assert not offenders, (
        "these runtime stores are tracked by git and would be published:\n  "
        + "\n  ".join(offenders)
        + "\nUntrack with `git rm --cached <path>` -- adding them to .gitignore "
        "is not enough once git already tracks them."
    )


def test_the_demo_generator_is_reproducible():
    """§5: "Same seed -> byte-identical output."

    `data/weekly/*.csv` are tracked, and the generator overwrites them. Without a
    seed every run produced a diff of meaningless number churn -- including the
    run the E2E suite does to seed itself. A repository that reports changes
    nobody made trains people to discard changes without reading them.
    """
    import csv
    import io
    import random

    from src.api.routers.simulator import (
        DEFAULT_SEED,
        DEMO_EMPLOYEES,
        _assign_archetype,
        _week_metrics,
    )

    def cohort(seed: int) -> str:
        rng = random.Random(seed)
        profiles = {name: _assign_archetype(rng) for name in DEMO_EMPLOYEES}
        out = io.StringIO()
        writer = csv.writer(out)
        for week in range(1, 5):
            for employee, archetype in profiles.items():
                writer.writerow([employee, *_week_metrics(archetype, week, rng)])
        return out.getvalue()

    assert cohort(DEFAULT_SEED) == cohort(DEFAULT_SEED), (
        "the same seed produced different data"
    )
    assert cohort(DEFAULT_SEED) != cohort(DEFAULT_SEED + 1), (
        "the seed has no effect -- the generator is not actually seeded"
    )
