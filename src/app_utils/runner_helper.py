# src/app_utils/runner_helper.py
# Provides a pre-session-creating runner wrapper compatible with ADK 2.0 InMemoryRunner.
#
# STRIDE fixes & Quota resiliency (2026-06-29):
#   - Pre-creates session before running to avoid SessionNotFoundError.
#   - Implements model fallback/retry mechanism to handle quota exhaustion (429/400).
#   - Monkey-patches Gemini model class to force explicit API key injection, bypassing
#     any standard environment variable warnings or lookup errors inside google-genai.
#
# API-reliance reduction (2026-07-20):
#   - Local-Only Mode: when enabled (data/settings.json), skips every Gemini
#     attempt immediately and raises so callers fall through to their local
#     fallback tiers -- avoids spending quota on calls known to be blocked.
#   - Fail-fast on non-retryable errors: an invalid API key or permission
#     error will fail identically on all 9 fallback models, so retrying all
#     of them is pure waste. Detected and short-circuited immediately.
#   - Minimum-interval cooldown between consecutive calls to smooth bursts
#     that would otherwise trip a per-minute rate limit.

import contextlib
import json
import logging
import os
import tempfile
import threading
import time

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import Client, types
from google.genai import types as genai_types

from src.app_utils.settings import is_local_only_mode

logger = logging.getLogger(__name__)

# Error markers that indicate the problem is with the account/key itself,
# not the specific model -- every one of the 9 fallback models would fail
# the same way, so there is no point retrying them.
_NON_RETRYABLE_MARKERS = (
    "api_key_invalid",
    "permission_denied",
    "unauthenticated",
    "invalid api key",
    "api key not valid",
)


def _is_non_retryable_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _NON_RETRYABLE_MARKERS)


# Minimum spacing enforced between consecutive Gemini calls (across every
# agent, globally) to reduce burst-triggered 429s when many employees/weeks
# are scored back-to-back in a single pipeline run.
_MIN_CALL_INTERVAL_SECONDS = 0.6
_last_call_time = 0.0
_rate_limit_lock = threading.Lock()


def _wait_for_call_slot() -> None:
    global _last_call_time
    with _rate_limit_lock:
        now = time.time()
        wait_needed = _MIN_CALL_INTERVAL_SECONDS - (now - _last_call_time)
        if wait_needed > 0:
            time.sleep(wait_needed)
        _last_call_time = time.time()


METRICS_FILE = os.environ.get("API_METRICS_PATH", "api_metrics.json")

# Serialises the read-modify-write below. Without it, concurrent callers (the
# background pipeline thread, per-attempt executor threads, and any parallel
# request) interleave read/increment/write and silently lose counts, so the
# badge under-reports real usage.
_metrics_lock = threading.Lock()


def _update_metrics(success: bool) -> None:
    """Track API success vs. local-fallback counts for the UI's status badge.

    Also called for Local-Only Mode skips (as a "rejected"/fallback event)
    so the badge accurately reflects how often the system is running on
    local logic instead of live Gemini calls.
    """
    try:
        with _metrics_lock:
            metrics = {"success": 0, "rejected": 0}
            if os.path.exists(METRICS_FILE):
                try:
                    with open(METRICS_FILE, encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        metrics.update(
                            {
                                k: int(loaded.get(k, 0) or 0)
                                for k in ("success", "rejected")
                            }
                        )
                except (json.JSONDecodeError, ValueError, TypeError):
                    # Corrupt/truncated file (e.g. killed mid-write by an
                    # older build): restart the counters rather than crash the
                    # call this is only instrumenting.
                    logger.warning(
                        "%s was unreadable; resetting API counters.", METRICS_FILE
                    )

            metrics["success" if success else "rejected"] += 1

            # Atomic replace: a crash can no longer leave a half-written file,
            # and readers never observe a partial JSON document.
            directory = os.path.dirname(os.path.abspath(METRICS_FILE))
            os.makedirs(directory, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=directory, prefix=".api_metrics_", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(metrics, f)
                os.replace(tmp_path, METRICS_FILE)
            except Exception:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
                raise
    except Exception:
        # Instrumentation must never break the request it is measuring.
        logger.debug("Could not update API metrics.", exc_info=True)


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

# Single source of truth for the Gemini fallback sequence -- the UI's
# model-status view reads the full multi-provider chain via
# get_model_status() / get_fallback_sequence() instead of keeping its own
# separate hardcoded copy in sync by hand.
FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.1-pro",
    "gemini-3.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


# ---------------------------------------------------------------------------
# Multi-provider fallback: Gemini -> Groq (free) -> local Ollama -> (caller's
# local ML tiers). Non-Gemini rungs are appended ONLY when their env config
# is present, so a Gemini-only deployment behaves exactly as before and the
# existing test-suite is unaffected. This means "Gemini quota exhausted" is
# no longer fatal -- other free/local providers pick up automatically before
# anything drops to the non-LLM fallback.
# ---------------------------------------------------------------------------
def _litellm_available() -> bool:
    """Whether ADK's LiteLlm wrapper (and litellm) can be imported.

    litellm ships transitively with google-adk, but we guard anyway so a
    stripped-down fork without it simply runs Gemini-only rather than crashing.
    """
    import importlib.util

    try:
        return importlib.util.find_spec("google.adk.models.lite_llm") is not None
    except Exception:
        return False


def _groq_models() -> list[str]:
    """Groq free-tier fallback model ids, active only when GROQ_API_KEY is set.

    Groq is OpenAI-compatible and litellm reads GROQ_API_KEY from the env
    automatically. Override the default list with a comma-separated GROQ_MODELS
    env var (litellm ids, e.g. "groq/llama-3.3-70b-versatile,groq/llama-3.1-8b-instant").
    Returns [] when unconfigured so Gemini-only setups are wholly unaffected.
    """
    if not os.environ.get("GROQ_API_KEY") or not _litellm_available():
        return []
    raw = os.environ.get("GROQ_MODELS", "groq/llama-3.3-70b-versatile")
    return [m.strip() for m in raw.split(",") if m.strip()]


def _ollama_models() -> list[str]:
    """Local Ollama fallback model ids, active only when OLLAMA_MODEL is set.

    Runs entirely on-machine: no API key, no rate limit, no employee data ever
    leaves the host -- a privacy upgrade over any hosted API. Requires a running
    Ollama server with the model pulled, e.g. `ollama pull llama3.2`, then set
    OLLAMA_MODEL=ollama_chat/llama3.2 (comma-separated for several).
    """
    if not _litellm_available():
        return []
    raw = os.environ.get("OLLAMA_MODEL", "").strip()
    if not raw:
        return []
    return [m.strip() for m in raw.split(",") if m.strip()]


def get_fallback_sequence() -> list[str]:
    """The full, ordered model fallback chain across every configured provider.

    Order encodes strategy: Gemini first (primary), then Groq (free, separate
    quota bucket), then local Ollama (always-available offline floor). Read at
    call time so toggling env config takes effect without a restart.
    """
    return list(FALLBACK_MODELS) + _groq_models() + _ollama_models()


def _provider_of(model_name: str) -> str:
    """Classify a candidate model id by provider ('gemini' / 'groq' / 'ollama')."""
    if model_name.startswith("groq/"):
        return "groq"
    if model_name.startswith(("ollama_chat/", "ollama/")):
        return "ollama"
    return "gemini"


def _build_model(model_name: str):
    """Return the correct ADK model object for a fallback candidate id.

    Gemini names use the native (monkey-patched) Gemini class; everything else
    goes through ADK's LiteLlm wrapper. litellm is imported lazily so pure-Gemini
    runs never pay its import cost.
    """
    provider = _provider_of(model_name)
    if provider == "gemini":
        return Gemini(model=model_name)

    from google.adk.models.lite_llm import LiteLlm

    if provider == "ollama":
        api_base = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
        return LiteLlm(model=model_name, api_base=api_base)
    return LiteLlm(model=model_name)  # groq / other OpenAI-compatible providers


def get_model_status() -> dict:
    """Expose the real, current model-fallback state for the UI's diagnostics
    view -- which models are actually in a 60s exhaustion cooldown right now
    (not a guess derived from a cumulative counter), and which one last
    succeeded. Does not reflect Local-Only Mode; callers should check
    `is_local_only_mode()` separately since that skips this logic entirely.
    """
    now = time.time()
    exhausted = [
        {"model": model, "cooldown_remaining_seconds": max(0, round(expiry - now))}
        for model, expiry in _EXHAUSTED_MODELS.items()
        if expiry > now
    ]
    return {
        "fallback_sequence": get_fallback_sequence(),
        "last_successful_model": _LAST_SUCCESSFUL_MODEL,
        "exhausted_models": exhausted,
    }


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

    Raises immediately, without attempting any model, if Local-Only Mode is
    enabled -- every caller in this codebase already has a local fallback
    path for exactly this exception.
    """
    import asyncio

    global _LAST_SUCCESSFUL_MODEL, _EXHAUSTED_MODELS

    if is_local_only_mode():
        _update_metrics(False)
        raise RuntimeError(
            "Local-Only Mode is enabled -- skipping Gemini API calls by user choice."
        )

    # 1. Determine model fallback sequence across every configured provider
    #    (Gemini, then Groq, then Ollama -- see get_fallback_sequence()).
    fallback_models = get_fallback_sequence()

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
        candidates = [_LAST_SUCCESSFUL_MODEL] + [
            m for m in available_models if m != _LAST_SUCCESSFUL_MODEL
        ]
    else:
        current_model_name = getattr(agent.model, "model", "gemini-2.5-flash")
        candidates = available_models.copy()
        if (
            current_model_name not in candidates
            and current_model_name not in _EXHAUSTED_MODELS
        ):
            candidates.insert(0, current_model_name)

    from concurrent.futures import ThreadPoolExecutor

    last_exception = None

    async def _async_run(model_name: str) -> str:
        # Build a request-local Agent copy for this attempt instead of mutating
        # the shared, module-level `agent` object in place. The agents in this
        # codebase are module-level singletons imported by multiple request
        # handlers; reassigning `agent.model` directly would let two concurrent
        # FastAPI requests race on the same attribute and run with each
        # other's model mid-flight.
        run_agent = Agent(
            name=agent.name,
            model=_build_model(model_name),
            instruction=agent.instruction,
        )

        # Re-create runner so the new model configuration is fully initialized.
        runner = InMemoryRunner(agent=run_agent, app_name=app_name)

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

    # Providers whose shared credential/config just failed non-retryably --
    # every remaining model of that provider would fail identically, so we skip
    # them, but keep trying the OTHER providers in the chain.
    dead_providers: set[str] = set()

    for model_name in candidates:
        if _provider_of(model_name) in dead_providers:
            continue
        _wait_for_call_slot()  # smooth bursts across consecutive calls
        try:
            # Spawn a thread to guarantee there is no running loop in the execution context
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_execute_in_new_loop, model_name)
                result = future.result()
                # Successfully completed! Store this model as the current working model
                _LAST_SUCCESSFUL_MODEL = model_name
                _update_metrics(True)
                return result

        except Exception as e:
            last_exception = e

            # Mark model as exhausted for 60 seconds to save looping time across other requests
            _EXHAUSTED_MODELS[model_name] = time.time() + 60

            # If the current successful model failed, clear it
            if _LAST_SUCCESSFUL_MODEL == model_name:
                _LAST_SUCCESSFUL_MODEL = None

            if _is_non_retryable_error(e):
                # An invalid key / permission error fails identically for every
                # model of the SAME provider (shared credential), so skip that
                # provider's remaining candidates -- but still fall through to
                # the other providers in the chain (Groq/Ollama may be fine even
                # if Gemini's key is bad, and vice-versa).
                provider = _provider_of(model_name)
                dead_providers.add(provider)
                logger.error(
                    "Non-retryable error (%s) on %s model %s -- skipping that "
                    "provider's remaining models; continuing to other providers.",
                    type(e).__name__,
                    provider,
                    model_name,
                )
                continue

            logger.warning(
                "Model %s failed with %s. Trying next fallback candidate.",
                model_name,
                type(e).__name__,
            )

    # Every candidate across every provider failed -> the caller falls through
    # to its own local (non-LLM) fallback tiers.
    if last_exception:
        logger.error("All provider fallback models exhausted. Raising last exception.")
        _update_metrics(False)
        raise last_exception

    return ""
