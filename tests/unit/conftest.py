# No unit test may reach a language provider.
#
# PRODUCTION_EVOLUTION_PROMPT.md §6.3: "CI must never call a real LLM." That was
# being honoured by each test remembering to stub its own seam, which is the
# same discipline that produced blocker B1 -- it holds until somebody forgets,
# and then nothing says so.
#
# It had already failed twice. The Phase 4 security suite spawned real pipeline
# threads after a refactor moved the name it was patching, and a cohort test
# reached Gemini the moment its fixture happened to confirm a signal. Neither
# was visible in the output beyond a slower run and some async warnings.
#
# So the block is central and default-on. A test that wants to exercise the LLM
# path supplies its own stub, which overrides this one for that test.

import pytest

#: Every module that owns a provider call.
_LLM_MODULES = (
    "src.orchestrator_agent",
    "src.risk_scorer_agent",
    "src.trend_detector_agent",
    "src.manager_briefing_agent",
    "src.api.routers.ingest",
)


class LiveProviderCallAttempted(AssertionError):
    """Raised instead of making a network call from a unit test."""


@pytest.fixture(autouse=True)
def _block_live_providers(monkeypatch):
    """Replace every `run_agent_sync` with something that refuses loudly.

    Refusing by RAISING rather than returning a canned string is deliberate:
    the agents all catch provider errors and fall back, so a stub that returned
    text would silently exercise a path the test did not intend. An exception
    lands in the same handler a real outage would, which is the honest
    simulation, and any test that genuinely wanted the LLM path fails with a
    message naming the problem.
    """
    import importlib

    def _refuse(*args, **kwargs):
        raise LiveProviderCallAttempted(
            "A unit test tried to call a live language provider. Stub the seam "
            "for this test (DEFAULT_SCORER / DEFAULT_ENRICHER, or patch "
            "run_agent_sync yourself). See PRODUCTION_EVOLUTION_PROMPT.md 6.3."
        )

    for name in _LLM_MODULES:
        try:
            module = importlib.import_module(name)
        except Exception:
            continue
        if hasattr(module, "run_agent_sync"):
            monkeypatch.setattr(module, "run_agent_sync", _refuse, raising=False)

    # The provider chain itself, in case a module reaches it directly.
    try:
        from src.app_utils import runner_helper

        monkeypatch.setattr(runner_helper, "run_agent_sync", _refuse, raising=False)
    except Exception:  # pragma: no cover - import guarded above
        pass


@pytest.fixture(autouse=True)
def _isolate_writable_state(monkeypatch, tmp_path):
    """Keep stateful stores out of the developer's real data directory.

    A security test cleared `data/memory` once before this existed. Regenerable
    artefacts, no tracked files lost -- and a test suite that destroys local
    state to prove a point has failed at the thing it was proving.

    Only the databases are redirected here. Tests that need `MEMORY_DIR` moved
    do it themselves, because several assert on files they wrote.

    This did not work until `src/config.py` existed: the stores captured their
    paths into module constants at IMPORT time, which is before any fixture
    runs, so every setenv below was ignored and the suite wrote to the real
    `data/` directory. The docstring described a protection that was not
    running. Paths are resolved per call now, and a probe confirms it.
    """
    monkeypatch.setenv("FEEDBACK_DB_PATH", str(tmp_path / "feedback.db"))
    monkeypatch.setenv("INTERVENTION_DB_PATH", str(tmp_path / "interventions.db"))
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path / "models"))
    # The access trail, added once the redirection above started working. This
    # is the record of who looked at whose assessment; a test run must not
    # append to the real one.
    monkeypatch.setenv("AUDIT_DB_PATH", str(tmp_path / "audit.db"))
