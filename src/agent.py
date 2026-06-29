# Quiet Quitting Detector - Root Agent
# Coordinates access to the multi-agent quiet quitting detection system.

from google.adk.apps import App

from src.orchestrator_agent import orchestrator_agent, run_orchestrator

# Root agent is the orchestrator agent
root_agent = orchestrator_agent

# Expose the pipeline execution function as a tool
root_agent.tools = [run_orchestrator]

app = App(
    root_agent=root_agent,
    name="quiet_quitting_detector_app",
)
