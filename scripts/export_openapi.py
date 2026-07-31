#!/usr/bin/env python
"""Write the OpenAPI schema to openapi.json.

    uv run python scripts/export_openapi.py

The frontend's types are generated from this file (`npm run generate:api`), so
exporting it in CI rather than committing it is what stops the two drifting:
there is no version of the schema that is not the one the app actually serves.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import app

OUTPUT = pathlib.Path(__file__).resolve().parents[1] / "openapi.json"


def main() -> int:
    schema = app.openapi()
    OUTPUT.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    paths = len(schema.get("paths", {}))
    print(f"Wrote {OUTPUT.name}: {paths} path(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
