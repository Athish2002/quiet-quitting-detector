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


# Global tracker for the last known successful model during this runtime session
_LAST_SUCCESSFUL_MODEL = None
_EXHAUSTED_MODELS = {}


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
    import asyncio
    import time
    global _LAST_SUCCESSFUL_MODEL, _EXHAUSTED_MODELS

    # 1. Determine model fallback sequence based on available Text-out models.
    fallback_models = [
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.1-pro",
        "gemini-3.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite"
    ]

    current_time = time.time()
    # Prune expired exhausted models (exhaustion lasts for 60 seconds)
    expired = [m for m, exp in _EXHAUSTED_MODELS.items() if exp < current_time]
    for m in expired:
        del _EXHAUSTED_MODELS[m]

    # Filter out currently exhausted models
    available_models = [m for m in fallback_models if m not in _EXHAUSTED_MODELS]
    if not available_models:
        # If ALL models are exhausted, try them anyway just in case the limits reset early
        available_models = fallback_models

    # Prioritize the last known working model if set to avoid redundant 429 delays
    if _LAST_SUCCESSFUL_MODEL and _LAST_SUCCESSFUL_MODEL in available_models:
        candidates = [_LAST_SUCCESSFUL_MODEL] + [m for m in available_models if m != _LAST_SUCCESSFUL_MODEL]
    else:
        current_model_name = getattr(agent.model, "model", "gemini-2.5-flash")
        candidates = available_models.copy()
        if current_model_name not in candidates and current_model_name not in _EXHAUSTED_MODELS:
            candidates.insert(0, current_model_name)

    from concurrent.futures import ThreadPoolExecutor

    last_exception = None

    async def _async_run(model_name: str) -> str:
        # Set the model on the agent for this attempt.
        agent.model = Gemini(model=model_name)

        # Re-create runner so the new model configuration is fully initialized.
        runner = InMemoryRunner(agent=agent, app_name=app_name)

        # Pre-create the session before runner.run_async().
        await runner.session_service.create_session(
            app_name=runner.app_name,
            user_id=user_id,
            session_id=session_id,
        )

        response_text = ""
        # run_async yields events and propagates exceptions directly
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            ),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text

        return response_text.strip()

    def _execute_in_new_loop(model_name: str):
        # Create a new event loop for this thread to avoid event loop conflicts in FastAPI
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_async_run(model_name))
        finally:
            loop.close()

    def update_metrics(success: bool):
        metrics_file = "api_metrics.json"
        try:
            import json, os
            metrics = {"success": 0, "rejected": 0}
            if os.path.exists(metrics_file):
                with open(metrics_file, "r") as f:
                    metrics = json.load(f)
            if success:
                metrics["success"] += 1
            else:
                metrics["rejected"] += 1
            with open(metrics_file, "w") as f:
                json.dump(metrics, f)
        except Exception:
            pass

    for i, model_name in enumerate(candidates):
        try:
            # Spawn a thread to guarantee there is no running loop in the execution context
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_execute_in_new_loop, model_name)
                result = future.result()
                # Successfully completed! Store this model as the current working model
                _LAST_SUCCESSFUL_MODEL = model_name
                update_metrics(True)
                return result

        except Exception as e:
            last_exception = e
            import time
            
            # Mark model as exhausted for 60 seconds to save looping time across other requests
            _EXHAUSTED_MODELS[model_name] = time.time() + 60
            
            # If the current successful model failed, clear it
            if _LAST_SUCCESSFUL_MODEL == model_name:
                _LAST_SUCCESSFUL_MODEL = None
                
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
                update_metrics(False)

    # If all models failed, propagate the last exception
    if last_exception:
        raise last_exception

    return ""
