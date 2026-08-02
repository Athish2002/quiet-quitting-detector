# src/config.py
# Every environment variable this application reads, in one validated model.
#
# §4 wants "Pydantic v2 models at every boundary", and the environment is a
# boundary -- it is untyped input from outside the process, which is exactly
# what the rest of the codebase refuses to accept anywhere else.
#
# Two things were actually wrong before this existed, not just untidy:
#
# 1. A typo in a path variable was indistinguishable from not setting it. Bad
#    values were absorbed by `os.environ.get(NAME, default)` and the process
#    started happily on the default, which is the worst outcome: it looks like
#    it worked.
# 2. Several modules captured their configuration into a module-level constant
#    AT IMPORT TIME. `tests/unit/conftest.py` redirects FEEDBACK_DB_PATH,
#    INTERVENTION_DB_PATH and MODEL_REGISTRY_DIR at tmp_path to keep the suite
#    out of the developer's real data directory -- and it had no effect,
#    because the constants had already been read when the test module was
#    imported. The fixture's docstring described a protection that was not
#    running.
#
# So `get_settings()` reads the environment on every call rather than caching a
# snapshot. It costs a few microseconds against calls that all do file I/O
# anyway, and it means there is exactly one answer to "what is this configured
# to right now" -- the cached-snapshot version is how (2) happened.
#
# NOT covered here, deliberately: the variables in `src/app_utils/telemetry.py`
# and `services.py`. Those are not read by this application -- they are written
# for the ADK and OpenTelemetry SDKs, which read the environment themselves. A
# model that "validated" them would be describing someone else's contract.
#
# `pydantic-settings` is the obvious library for this and is not used: this
# environment cannot install packages (see PROGRESS.md), and a config layer that
# only works on a machine with network access is worse than sixty lines of
# stdlib. Swapping it in later is a mechanical change -- the field definitions
# and validators below transfer as they are.

from __future__ import annotations

import json
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

#: Where the process refuses to start rather than guess.
API_KEYS_ENV = "API_KEYS"
WEBHOOK_SECRET_ENV = "WEBHOOK_SIGNING_SECRET"

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_VALID_ROLES = ("viewer", "manager", "admin")

#: Long enough that a brute-force over a name list is not the cheaper attack.
#: A short salt is not a weak secret, it is a decorative one.
MIN_SECRET_LENGTH = 16


class ConfigError(RuntimeError):
    """Configuration is invalid and the process must not continue.

    Raised at startup, with every problem listed rather than the first one --
    fixing a deployment three variables at a time, one restart each, is how
    people give up and set everything to the default.
    """


class ApiKeySpec(BaseModel):
    """One configured API key, as it appears in `API_KEYS`.

    Only the SHA-256 lives here. The plaintext key is never stored, never
    logged, and never compared with `==`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    role: str
    key_sha256: str

    @field_validator("role")
    @classmethod
    def _known_role(cls, value: str) -> str:
        role = value.strip().lower()
        if role not in _VALID_ROLES:
            raise ValueError(f"unknown role {value!r}; expected one of {_VALID_ROLES}")
        return role

    @field_validator("key_sha256")
    @classmethod
    def _looks_like_a_digest(cls, value: str) -> str:
        digest = value.strip().lower()
        if not _SHA256_HEX.match(digest):
            # Catches the mistake that matters: pasting the KEY here instead of
            # its hash. That configuration authenticates nobody, and the symptom
            # is a 401 that looks like the key is wrong.
            raise ValueError("must be a 64-character SHA-256 hex digest")
        return digest


class Settings(BaseModel):
    """The environment, parsed and checked once.

    Fields are grouped the way the deployment checklist is: what protects
    people, where state is written, and which providers are reachable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- security ------------------------------------------------------------

    #: Empty means no keys are configured, which is NOT open access: the key
    #: ring generates a temporary admin key and says so loudly at startup.
    api_keys: tuple[ApiKeySpec, ...] = ()

    #: Without this, pseudonymous surrogate IDs are reversible by brute force
    #: over a list of names -- i.e. not pseudonymous. Empty is allowed and
    #: warned about, because refusing to start would make the demo unrunnable;
    #: `docs/LIMITATIONS.md` records that this must be set before real data.
    identity_salt: str = ""

    webhook_signing_secret: str = ""

    #: Never "*". With credentials enabled a wildcard lets any origin drive an
    #: authenticated session, which is the whole attack.
    allow_origins: tuple[str, ...] = (
        "http://localhost:8000",
        "http://localhost:5173",
    )

    # --- storage -------------------------------------------------------------

    feedback_db: str = os.path.join("data", "feedback.db")
    intervention_db: str = os.path.join("data", "interventions.db")
    model_registry_dir: str = os.path.join("data", "models")
    audit_db: str = os.path.join("data", "audit.db")
    identity_map: str = os.path.join("data", "identity_map.json")
    api_metrics: str = "api_metrics.json"
    #: Default-deny, and the source of truth for what may be persisted.
    data_allowlist: str = os.path.join("config", "data_allowlist.json")

    # --- providers -----------------------------------------------------------

    #: GEMINI_API_KEY wins; GOOGLE_API_KEY is the ADK's own name for it.
    gemini_api_key: str = ""
    groq_api_key: str = ""
    groq_models: tuple[str, ...] = ("groq/llama-3.3-70b-versatile",)
    ollama_model: str = ""
    ollama_api_base: str = "http://localhost:11434"

    # --- service -------------------------------------------------------------

    app_url: str = "http://0.0.0.0:8000"
    agent_version: str = "0.1.0"

    @field_validator("allow_origins")
    @classmethod
    def _explicit_origins_only(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for origin in value:
            if origin == "*":
                raise ValueError(
                    "'*' is not allowed: CORS runs with credentials, so a "
                    "wildcard would let any origin drive an authenticated "
                    "session. List the origins."
                )
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"{origin!r} has no scheme; expected http(s)://")
        return value

    @field_validator("webhook_signing_secret", "identity_salt")
    @classmethod
    def _long_enough_to_be_a_secret(cls, value: str) -> str:
        if value and len(value) < MIN_SECRET_LENGTH:
            raise ValueError(
                f"is set but is only {len(value)} characters; "
                f"use at least {MIN_SECRET_LENGTH} or leave it unset"
            )
        return value

    @field_validator(
        "feedback_db",
        "intervention_db",
        "model_registry_dir",
        "audit_db",
        "identity_map",
        "api_metrics",
        "data_allowlist",
    )
    @classmethod
    def _a_path_or_nothing(cls, value: str) -> str:
        # An empty override is the shape a shell mistake takes -- `FOO=$BAR`
        # with BAR unset. Falling back to the default here would write real
        # state to the developer's data directory during a test run, which is
        # the bug this module exists to stop.
        if not value.strip():
            raise ValueError("is set to an empty value; unset it to use the default")
        return value.strip()

    @property
    def has_provider_key(self) -> bool:
        """Whether any LLM provider is reachable at all."""
        return bool(self.gemini_api_key or self.groq_api_key or self.ollama_model)

    def startup_summary(self) -> str:
        """What is configured, for the boot log. Never a secret value."""
        return (
            f"Config: {len(self.api_keys)} API key(s), "
            f"identity salt {'set' if self.identity_salt else 'NOT SET'}, "
            f"webhook secret {'set' if self.webhook_signing_secret else 'not set'}, "
            f"origins {list(self.allow_origins)}, "
            f"provider {'configured' if self.has_provider_key else 'none (local only)'}."
        )


def _split(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _parse_api_keys(raw: str) -> list[dict[str, Any]]:
    """`API_KEYS` as a list of dicts, or a ConfigError explaining what it is."""
    if not raw.strip():
        return []
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"{API_KEYS_ENV} is not valid JSON: {exc.msg} at position {exc.pos}. "
            'Expected [{"id": "...", "role": "admin", "key_sha256": "<64 hex>"}].'
        ) from exc
    if not isinstance(entries, list):
        raise ConfigError(f"{API_KEYS_ENV} must be a JSON array, not a JSON object.")
    if any(not isinstance(entry, dict) for entry in entries):
        raise ConfigError(f"{API_KEYS_ENV} must be an array of objects.")
    return entries


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build `Settings` from the environment, or raise `ConfigError`.

    Every problem is reported together. A deployment fixed one variable per
    restart is a deployment nobody finishes fixing.
    """
    source = os.environ if env is None else env

    def value(name: str, default: str = "") -> str:
        return source.get(name, default).strip()

    fields: dict[str, Any] = {
        "api_keys": _parse_api_keys(source.get(API_KEYS_ENV, "")),
        "identity_salt": value("IDENTITY_SALT"),
        "webhook_signing_secret": value(WEBHOOK_SECRET_ENV),
        "gemini_api_key": value("GEMINI_API_KEY") or value("GOOGLE_API_KEY"),
        "groq_api_key": value("GROQ_API_KEY"),
        "ollama_model": value("OLLAMA_MODEL"),
    }

    # Only override a default when the variable is actually present: passing
    # "" for an unset variable would turn every default into the empty string
    # and trip the validators above for no reason.
    optional = {
        "allow_origins": "ALLOW_ORIGINS",
        "groq_models": "GROQ_MODELS",
        "feedback_db": "FEEDBACK_DB_PATH",
        "intervention_db": "INTERVENTION_DB_PATH",
        "model_registry_dir": "MODEL_REGISTRY_DIR",
        "audit_db": "AUDIT_DB_PATH",
        "identity_map": "IDENTITY_MAP_PATH",
        "api_metrics": "API_METRICS_PATH",
        "data_allowlist": "DATA_ALLOWLIST_PATH",
        "ollama_api_base": "OLLAMA_API_BASE",
        "app_url": "APP_URL",
        "agent_version": "AGENT_VERSION",
    }
    for field, name in optional.items():
        if name in source:
            raw = source[name]
            fields[field] = (
                _split(raw) if field in {"allow_origins", "groq_models"} else raw
            )

    try:
        return Settings(**fields)
    except ValidationError as exc:
        raise ConfigError(_readable(exc, optional)) from exc


def _readable(exc: ValidationError, optional: dict[str, str]) -> str:
    """Pydantic's report, rewritten in terms of the variable names people set.

    "allow_origins.0" means nothing to whoever is editing a deployment; the
    variable they have to change is ALLOW_ORIGINS.
    """
    names = {
        **optional,
        "api_keys": API_KEYS_ENV,
        "identity_salt": "IDENTITY_SALT",
        "webhook_signing_secret": WEBHOOK_SECRET_ENV,
        "gemini_api_key": "GEMINI_API_KEY",
        "groq_api_key": "GROQ_API_KEY",
        "ollama_model": "OLLAMA_MODEL",
    }
    lines = []
    for error in exc.errors():
        location = error["loc"]
        variable = names.get(str(location[0]), str(location[0]).upper())
        where = "".join(f"[{part}]" for part in location[1:])
        message = error["msg"].removeprefix("Value error, ")
        lines.append(f"  {variable}{where}: {message}")
    return "Invalid configuration:\n" + "\n".join(lines)


def get_settings() -> Settings:
    """The current configuration. Read fresh -- see the note at the top."""
    return load_settings()
