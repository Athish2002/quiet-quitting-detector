# Quiet Quitting Detector - Root Agent
# Coordinates access to the multi-agent quiet quitting detection system.

from google.adk.apps import App

from src.orchestrator_agent import orchestrator_agent, run_orchestrator


def run_pipeline(
    weekly_folder: str = "data/weekly", memory_folder: str = "data/memory"
) -> str:
    """Evaluate every employee in the weekly CSV folder and return the report.

    Each person is compared against their own earlier weeks, never against a
    cohort average, and a pattern must persist for two or more consecutive weeks
    before it is reported.

    Args:
        weekly_folder: Directory holding the weekly metric CSVs.
        memory_folder: Directory holding per-employee evaluation history.

    Returns:
        The cohort report as text.
    """
    # A wrapper, not an alias, and the reason is not cosmetic.
    #
    # `run_orchestrator` takes `progress_cb: Callable | None` so the API can
    # drive a progress bar. ADK generates a JSON Schema for every tool
    # parameter, and a callable has no JSON Schema -- so registering
    # `run_orchestrator` directly raised PydanticInvalidForJsonSchema and the
    # ROOT AGENT FAILED TO RUN AT ALL. Every ADK entrypoint was dead: `adk run`,
    # the A2A path, and the reasoning-engine adapter.
    #
    # It was invisible to the unit suite because nothing there builds the tool
    # declaration; the integration tests caught it, and they are excluded from
    # CI because they need a live LLM. Hence `tests/unit/test_agent_tools.py`,
    # which builds the declaration and needs no network.
    return run_orchestrator(weekly_folder=weekly_folder, memory_folder=memory_folder)


root_agent = orchestrator_agent

# Only JSON-schema-expressible parameters may appear on a tool.
root_agent.tools = [run_pipeline]

app = App(
    root_agent=root_agent,
    name="quiet_quitting_detector_app",
)
