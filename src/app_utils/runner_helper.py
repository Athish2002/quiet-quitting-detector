# src/app_utils/runner_helper.py
# Provides a pre-session-creating runner wrapper compatible with ADK 2.0 InMemoryRunner.
#
# STRIDE fixes & Quota resiliency (2026-06-29):
#   - Pre-creates session before running to avoid SessionNotFoundError.
#   - Implements model fallback/retry mechanism to handle quota exhaustion (429/400).
#   - Monkey-patches Gemini model class to force explicit API key injection, bypassing
#     any standard environment variable warnings or lookup errors inside google-genai.

import logging
import os

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import Client, types
from google.genai import types as genai_types

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Monkey-patch: Force explicit api_key injection on GenAI Client initialization
# ---------------------------------------------------------------------------
def patched_api_client(self) -> Client:
    if not hasattr(self, "_cached_api_client"):
        base_url, api_version = self._base_url_and_api_version
        kwargs_for_http_options = {
            "headers": self._tracking_headers(),
            "retry_options": self.retry_options,
            "base_url": base_url,
        }
        if api_version:
            kwargs_for_http_options["api_version"] = api_version

        kwargs = {
            "http_options": genai_types.HttpOptions(**kwargs_for_http_options),
        }
        if self.model.startswith("projects/"):
            kwargs["vertexai"] = True

        # Explicitly pass api_key so it doesn't do environment lookup warning
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if key:
            kwargs["api_key"] = key

        self._cached_api_client = Client(**kwargs)
    return self._cached_api_client


def patched_live_api_client(self) -> Client:
    if not hasattr(self, "_cached_live_api_client"):
        base_url, _ = self._base_url_and_api_version
        kwargs = {
            "http_options": genai_types.HttpOptions(
                headers=self._tracking_headers(),
                api_version=self._live_api_version,
                base_url=base_url,
            )
        }
        if self.model.startswith("projects/"):
            kwargs["vertexai"] = True

        # Explicitly pass api_key
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if key:
            kwargs["api_key"] = key

        self._cached_live_api_client = Client(**kwargs)
    return self._cached_live_api_client


# Apply the patches dynamically to Gemini class in ADK
Gemini.api_client = property(patched_api_client)
Gemini._live_api_client = property(patched_live_api_client)


# ---------------------------------------------------------------------------
# Runner API
# ---------------------------------------------------------------------------
def run_agent_sync(
    agent: Agent,
    *,
    user_id: str,
    session_id: str,
    prompt: str,
    app_name: str = "quiet_quitting_detector",
) -> str:
    """Run an ADK agent synchronously and return the concatenated text response.

    If an API exception or rate/quota limit occurs, automatically switches the
    agent's model to a fallback candidate model and retries, ensuring robustness
    under heavy quota usage.
    """
    # 1. Determine model fallback sequence.
    current_model_name = getattr(agent.model, "model", "gemini-2.5-flash")
    fallback_models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-2.5-pro",
        "gemini-1.5-pro",
    ]

    candidates = [current_model_name]
    for m in fallback_models:
        if m not in candidates:
            candidates.append(m)

    last_exception = None

    for i, model_name in enumerate(candidates):
        try:
            # Set the model on the agent for this attempt.
            agent.model = Gemini(model=model_name)

            # Re-create runner so the new model configuration is fully initialized.
            runner = InMemoryRunner(agent=agent, app_name=app_name)

            # Pre-create the session before runner.run().
            runner.session_service.create_session_sync(
                app_name=runner.app_name,
                user_id=user_id,
                session_id=session_id,
            )

            events = list(
                runner.run(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=prompt)],
                    ),
                )
            )

            response_text = ""
            for event in events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text

            # Success!
            return response_text.strip()

        except Exception as e:
            last_exception = e
            # Only log candidate swap if we have fallback options remaining
            if i < len(candidates) - 1:
                print(
                    f"  [INFO] Model '{model_name}' execution failed (quota or error). "
                    f"Attempting fallback to '{candidates[i + 1]}'..."
                )
                logger.warning(
                    "Model %s failed with %s. Falling back to %s.",
                    model_name,
                    type(e).__name__,
                    candidates[i + 1],
                )
            else:
                logger.error("All fallback models exhausted. Raising last exception.")

    # If all models failed, propagate the last exception
    if last_exception:
        raise last_exception

    return ""
