# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# `app` is exported lazily (PEP 562).
#
# This used to be a plain `from .agent import app`, which meant that importing
# ANY submodule -- including the deliberately pure `src.domain` -- first executed
# `src/agent.py` and pulled in google.adk, google.genai, fastapi, starlette and
# dotenv. That defeats the point of the domain package: it could not be imported
# without the whole provider stack present, so a "pure" unit test was one import
# away from needing credentials, and CI was one import away from a live LLM
# (PRODUCTION_EVOLUTION_PROMPT.md 6.3).
#
# `tests/unit/test_domain_boundary.py` fails if this regresses.

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type-checking only, never executed
    from .agent import app

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    if name == "app":
        from .agent import app as _app

        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
