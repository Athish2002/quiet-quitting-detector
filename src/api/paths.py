# src/api/paths.py
# Where things live on disk, in one place.
#
# These were module-level constants in `app.py`, which meant every router
# extracted from it would either import from the composition root (a circular
# import) or redeclare them (two copies that drift -- the B6 failure again, in
# miniature). One module both can import is the boring correct answer.
#
# Not a Settings model yet. §4 wants everything through a validated Pydantic
# `Settings` that fails fast on bad values, and that is a real piece of work
# touching every module that reads an env var. Doing it here, half, would leave
# two config mechanisms instead of one. Listed in docs/LIMITATIONS.md.

from __future__ import annotations

import os

MEMORY_DIR = "data/memory"
WEEKLY_DIR = "data/weekly"
REALTIME_DIR = "data/realtime"
REALTIME_MEMORY_DIR = "data/realtime_memory"

#: The simulator writes here so a "what-if" run can never overwrite a real
#: cohort employee's memory files -- the default simulator name is also a real
#: employee in the demo data.
SIMULATOR_MEMORY_DIR = "data/simulator_memory"

MAIN_REPORT = "engagement_report.txt"
REALTIME_REPORT = "realtime_engagement_report.txt"
THREAT_MODEL = "THREAT_MODEL.md"

#: Generous for a weekly metrics CSV, small enough that one request cannot
#: exhaust memory. The security middleware enforces the same cap on every route.
MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024


def memory_dir_for(scope: str) -> str:
    """The memory directory for a scope: 'realtime' or anything else (main)."""
    return REALTIME_MEMORY_DIR if scope == "realtime" else MEMORY_DIR


def ensure(*directories: str) -> None:
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
