# Every ADK tool must be declarable.
#
# ADK builds a JSON Schema from each tool's signature before the agent can run.
# A parameter with no JSON Schema representation -- a callable, an arbitrary
# object -- raises at declaration time and takes the WHOLE ROOT AGENT down, not
# just that tool. `adk run`, the A2A path and the reasoning-engine adapter all
# stop working together.
#
# That is exactly what happened: `run_orchestrator` was registered directly, and
# its `progress_cb: Callable | None` parameter (there so the API can drive a
# progress bar) made the declaration unbuildable. The failure was invisible to
# the unit suite because nothing in it built a declaration, and the integration
# tests that would have caught it are excluded from CI because they need a live
# LLM (§6.3).
#
# So this test builds the declaration and asserts nothing else -- no network, no
# credentials, no model call. It is the cheap check that the expensive suite was
# the only thing covering.

import pytest


def _root_agent_tools():
    from src.agent import root_agent

    return list(root_agent.tools or [])


def test_the_root_agent_registers_at_least_one_tool():
    assert _root_agent_tools(), "the root agent exposes no tools at all"


def test_every_registered_tool_can_be_declared():
    """The check that would have caught a dead root agent."""
    from google.adk.tools import FunctionTool

    failures = []
    for tool in _root_agent_tools():
        name = getattr(tool, "__name__", repr(tool))
        try:
            FunctionTool(tool)._get_declaration()
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")

    assert not failures, (
        "these tools cannot be declared to the model, which stops the ENTIRE "
        "root agent from running:\n  " + "\n  ".join(failures)
    )


def test_no_tool_parameter_is_a_callable():
    """The specific shape that broke it, named so the next person recognises it.

    A callable parameter is a natural thing to add -- a progress callback, a
    logger, an injected dependency -- and it is fatal here. Catching it by shape
    gives a message that says what to do instead.
    """
    import inspect

    offenders = []
    for tool in _root_agent_tools():
        signature = inspect.signature(tool)
        for parameter in signature.parameters.values():
            annotation = str(parameter.annotation)
            if "Callable" in annotation or "Coroutine" in annotation:
                offenders.append(f"{tool.__name__}({parameter.name}: {annotation})")

    assert not offenders, (
        "a tool parameter has no JSON Schema representation. Wrap the function "
        "in a thin tool that omits it rather than exposing it:\n  "
        + "\n  ".join(offenders)
    )


def test_the_tool_still_drives_the_real_pipeline(monkeypatch, tmp_path):
    """The wrapper must actually call the orchestrator, not just typecheck.

    A wrapper added to satisfy a schema is easy to get subtly wrong -- swallowing
    arguments, or drifting from the function it fronts.
    """
    import src.agent as agent_module

    seen = {}

    def _fake(weekly_folder, memory_folder, progress_cb=None):
        seen["weekly"] = weekly_folder
        seen["memory"] = memory_folder
        return "report text"

    monkeypatch.setattr(agent_module, "run_orchestrator", _fake)

    result = agent_module.run_pipeline(
        weekly_folder=str(tmp_path / "weekly"),
        memory_folder=str(tmp_path / "memory"),
    )

    assert result == "report text"
    assert seen["weekly"].endswith("weekly")
    assert seen["memory"].endswith("memory")


def test_the_tool_has_a_docstring_the_model_can_use():
    """ADK sends the docstring to the model as the tool description. An
    undocumented tool is one the model cannot decide when to call."""
    for tool in _root_agent_tools():
        doc = (tool.__doc__ or "").strip()
        assert len(doc) > 40, f"{tool.__name__} has no usable description"


@pytest.mark.parametrize("module", ["src.agent", "src.orchestrator_agent"])
def test_agent_modules_import_without_credentials(module):
    """Importing the agent must not require GCP credentials or a live provider.

    `src/fast_api_app.py` does (it calls google.auth.default() at import time),
    which is why the server integration tests cannot run in CI. The agent itself
    must not inherit that.
    """
    import importlib

    importlib.import_module(module)
