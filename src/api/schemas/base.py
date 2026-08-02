# src/api/schemas/base.py
# The one config every response model shares.

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ResponseModel(BaseModel):
    """Base for the response models in this package.

    `json_schema_serialization_defaults_required` puts fields that have defaults
    into the schema's `required` list. That is the truth about a response: the
    server serialises every field, defaulted or not, so `confidence` is always
    present and sometimes null -- it is never missing.

    Without it those fields generate as OPTIONAL TypeScript properties, and
    every consumer ends up writing `?? null` guards against an absence the API
    cannot produce. Guards for impossible states are how real ones stop being
    read.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
