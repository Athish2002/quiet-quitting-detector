# Tests for the multi-provider LLM fallback chain in runner_helper.
#
# These are pure-logic tests -- they exercise how the Gemini -> Groq -> Ollama
# candidate sequence is assembled and how each candidate maps to an ADK model
# object, WITHOUT making any live API call. The whole point of the feature is
# that non-Gemini providers only activate when their env config is present, so
# most tests assert that inclusion is env-gated and correctly ordered.

import importlib

import pytest

runner_helper = importlib.import_module("src.app_utils.runner_helper")


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    """Guarantee a deterministic starting point regardless of the real shell/.env."""
    for var in ("GROQ_API_KEY", "GROQ_MODELS", "OLLAMA_MODEL", "OLLAMA_API_BASE"):
        monkeypatch.delenv(var, raising=False)
    yield


def test_provider_of_classifies_correctly():
    assert runner_helper._provider_of("gemini-2.5-flash") == "gemini"
    assert runner_helper._provider_of("groq/llama-3.3-70b-versatile") == "groq"
    assert runner_helper._provider_of("ollama_chat/llama3.2") == "ollama"
    assert runner_helper._provider_of("ollama/llama3.2") == "ollama"


def test_fallback_sequence_is_gemini_only_by_default():
    seq = runner_helper.get_fallback_sequence()
    assert seq == list(runner_helper.FALLBACK_MODELS)
    assert all(runner_helper._provider_of(m) == "gemini" for m in seq)


def test_groq_appended_only_when_key_present(monkeypatch):
    assert runner_helper._groq_models() == []
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    assert runner_helper._groq_models() == ["groq/llama-3.3-70b-versatile"]


def test_groq_absent_when_models_set_but_no_key(monkeypatch):
    # Models configured but no key -> still disabled (nothing to authenticate with).
    monkeypatch.setenv("GROQ_MODELS", "groq/a")
    assert runner_helper._groq_models() == []


def test_groq_models_env_override_is_parsed(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODELS", "groq/a, groq/b ,groq/c ")
    assert runner_helper._groq_models() == ["groq/a", "groq/b", "groq/c"]


def test_ollama_appended_only_when_model_set(monkeypatch):
    assert runner_helper._ollama_models() == []
    monkeypatch.setenv("OLLAMA_MODEL", "ollama_chat/llama3.2")
    assert runner_helper._ollama_models() == ["ollama_chat/llama3.2"]


def test_full_chain_ordering_is_gemini_then_groq_then_ollama(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("OLLAMA_MODEL", "ollama_chat/llama3.2")
    seq = runner_helper.get_fallback_sequence()
    providers = [runner_helper._provider_of(m) for m in seq]
    rank = {"gemini": 0, "groq": 1, "ollama": 2}
    # Each provider's models form one contiguous block in the strategic order.
    assert providers == sorted(providers, key=lambda p: rank[p])
    assert {"gemini", "groq", "ollama"}.issubset(set(providers))
    # Gemini block is unchanged and still first.
    assert seq[: len(runner_helper.FALLBACK_MODELS)] == list(
        runner_helper.FALLBACK_MODELS
    )


def test_build_model_returns_native_gemini_for_gemini_ids():
    from google.adk.models import Gemini

    assert isinstance(runner_helper._build_model("gemini-2.5-flash"), Gemini)


def test_build_model_returns_litellm_for_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    from google.adk.models.lite_llm import LiteLlm

    assert isinstance(
        runner_helper._build_model("groq/llama-3.3-70b-versatile"), LiteLlm
    )


def test_build_model_returns_litellm_for_ollama():
    from google.adk.models.lite_llm import LiteLlm

    assert isinstance(runner_helper._build_model("ollama_chat/llama3.2"), LiteLlm)


def test_model_status_reflects_configured_providers(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    status = runner_helper.get_model_status()
    assert any(m.startswith("groq/") for m in status["fallback_sequence"])
