# The environment is untyped input from outside the process, and this is the
# suite that treats it that way.
#
# Most of these assert on a REFUSAL. A configuration mistake that is absorbed
# into a default is the expensive kind: the process starts, looks healthy, and
# is wrong in a way nobody discovers until someone is locked out or a test run
# has written to the real database.

import pytest
from pydantic import ValidationError

from src.config import (
    MIN_SECRET_LENGTH,
    ConfigError,
    Settings,
    get_settings,
    load_settings,
)

VALID_DIGEST = "a" * 64
LONG_SECRET = "x" * MIN_SECRET_LENGTH


def test_an_empty_environment_is_valid_and_says_what_is_missing():
    """The demo has to run with nothing configured. It must also SAY so."""
    settings = load_settings({})
    assert settings.api_keys == ()
    assert settings.identity_salt == ""
    assert settings.has_provider_key is False
    assert "NOT SET" in settings.startup_summary()
    assert "local only" in settings.startup_summary()


def test_the_summary_never_contains_a_secret_value():
    settings = load_settings(
        {
            "IDENTITY_SALT": "salt-value-nobody-should-see",
            "WEBHOOK_SIGNING_SECRET": "webhook-value-nobody-should-see",
            "GEMINI_API_KEY": "gemini-value-nobody-should-see",
        }
    )
    summary = settings.startup_summary()
    assert "nobody-should-see" not in summary
    assert "set" in summary


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
def test_a_wildcard_origin_is_refused():
    """CORS runs with credentials. `*` would let any origin drive a session."""
    with pytest.raises(ConfigError) as raised:
        load_settings({"ALLOW_ORIGINS": "*"})
    assert "ALLOW_ORIGINS" in str(raised.value)


def test_an_origin_without_a_scheme_is_refused():
    with pytest.raises(ConfigError) as raised:
        load_settings({"ALLOW_ORIGINS": "http://ok.example,evil.example"})
    assert "no scheme" in str(raised.value)


def test_origins_are_split_and_trimmed():
    settings = load_settings(
        {"ALLOW_ORIGINS": " https://a.example , https://b.example ,"}
    )
    assert settings.allow_origins == ("https://a.example", "https://b.example")


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
def test_malformed_api_keys_json_is_refused_rather_than_ignored():
    """The failure this exists for.

    Before, a typo here loaded no keys, printed a temporary key into a log
    nobody was watching, and rejected every real caller -- an outage that looks
    like a client problem.
    """
    with pytest.raises(ConfigError) as raised:
        load_settings({"API_KEYS": "[{not json"})
    assert "API_KEYS is not valid JSON" in str(raised.value)


def test_a_key_pasted_where_its_hash_belongs_is_refused():
    """The mistake that authenticates nobody and looks like a wrong key."""
    with pytest.raises(ConfigError) as raised:
        load_settings(
            {
                "API_KEYS": '[{"id": "a", "role": "admin", '
                '"key_sha256": "my-actual-secret-key"}]'
            }
        )
    assert "64-character SHA-256" in str(raised.value)


def test_an_unknown_role_is_refused():
    with pytest.raises(ConfigError) as raised:
        load_settings(
            {
                "API_KEYS": f'[{{"id": "a", "role": "root", "key_sha256": "{VALID_DIGEST}"}}]'
            }
        )
    assert "unknown role" in str(raised.value)


def test_every_problem_is_reported_together():
    """One restart per mistake is how people give up and use the defaults."""
    with pytest.raises(ConfigError) as raised:
        load_settings({"ALLOW_ORIGINS": "*", "IDENTITY_SALT": "short"})
    message = str(raised.value)
    assert "ALLOW_ORIGINS" in message and "IDENTITY_SALT" in message


def test_a_valid_key_ring_is_accepted_and_normalised():
    settings = load_settings(
        {
            "API_KEYS": '[{"id": "ci", "role": "ADMIN", '
            f'"key_sha256": "{VALID_DIGEST.upper()}"}}]'
        }
    )
    assert len(settings.api_keys) == 1
    assert settings.api_keys[0].role == "admin"
    assert settings.api_keys[0].key_sha256 == VALID_DIGEST


# ---------------------------------------------------------------------------
# Secrets and paths
# ---------------------------------------------------------------------------
def test_a_secret_too_short_to_be_one_is_refused():
    """Unset is a stated gap. Set-but-decorative is a false assurance."""
    with pytest.raises(ConfigError):
        load_settings({"IDENTITY_SALT": "x" * (MIN_SECRET_LENGTH - 1)})
    assert load_settings({"IDENTITY_SALT": LONG_SECRET}).identity_salt == LONG_SECRET


def test_an_empty_path_override_is_refused_rather_than_defaulted():
    """`FOO=$BAR` with BAR unset is the shape this takes.

    Falling back to the default would send real state to the developer's data
    directory during a test run, which is the failure that motivated this
    module.
    """
    with pytest.raises(ConfigError) as raised:
        load_settings({"FEEDBACK_DB_PATH": "   "})
    assert "FEEDBACK_DB_PATH" in str(raised.value)


def test_an_absent_variable_keeps_the_default_rather_than_becoming_empty():
    settings = load_settings({})
    assert settings.feedback_db.endswith("feedback.db")
    assert settings.groq_models  # not an empty tuple


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
def test_gemini_key_wins_over_the_adks_name_for_it():
    settings = load_settings({"GEMINI_API_KEY": "a", "GOOGLE_API_KEY": "b"})
    assert settings.gemini_api_key == "a"
    assert load_settings({"GOOGLE_API_KEY": "b"}).gemini_api_key == "b"


def test_any_configured_provider_counts_as_reachable():
    assert load_settings({"GROQ_API_KEY": "k"}).has_provider_key is True
    assert load_settings({"OLLAMA_MODEL": "ollama_chat/llama3.2"}).has_provider_key


# ---------------------------------------------------------------------------
# Reading, not caching
# ---------------------------------------------------------------------------
def test_settings_are_read_fresh_every_time(monkeypatch):
    """Not cached, on purpose.

    A cached snapshot is exactly how the test suite's own tmp_path redirection
    came to be silently ignored for three stores: the value was captured before
    the fixture that set it ever ran.
    """
    monkeypatch.setenv("FEEDBACK_DB_PATH", "first.db")
    assert get_settings().feedback_db == "first.db"
    monkeypatch.setenv("FEEDBACK_DB_PATH", "second.db")
    assert get_settings().feedback_db == "second.db"


def test_settings_are_immutable_once_built():
    settings = load_settings({})
    with pytest.raises(ValidationError):
        settings.identity_salt = "changed"  # type: ignore[misc]


def test_an_unknown_field_is_rejected():
    """`extra="forbid"`, so a renamed field fails here rather than silently
    reverting to a default at the call site."""
    # Through model_validate rather than the constructor: `ty` rejects the
    # unknown keyword at check time, which is the same guarantee one layer
    # earlier, and leaves nothing to assert at runtime.
    with pytest.raises(ValidationError):
        Settings.model_validate({"nonexistent_field": "x"})
