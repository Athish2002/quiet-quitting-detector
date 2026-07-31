# src/data_layer/coercion.py
# Tolerant value parsing for inconsistent real-world inputs.
#
# The failure this exists to prevent was reproduced first: a genuinely ABSENT
# metric was being written as a plausible-looking default ("tasks_completed=0",
# "weekly_hours=40"). Downstream, a fabricated 0 is indistinguishable from a
# real zero -- i.e. from total disengagement -- so incomplete data manufactured
# the exact signal the system is meant to detect. Missing data is the most
# common condition in real HR exports, so this was a false-positive engine.
#
# Rules:
#   * Missing stays missing (None). It is never defaulted into a value.
#   * Sentinels ("", "N/A", "null", "-", "unknown", "TBD") are missing, not 0.
#   * Units are normalised ("90m" -> 1.5h, "2,340" -> 2340, "95%" -> 95).
#   * Implausible values are rejected with a reason rather than clamped, so a
#     unit mix-up surfaces instead of silently becoming a signal.
# Every parse returns *why* it produced what it did, so completeness can be
# reported and thin records flagged low-confidence rather than scored as fact.

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum

_SENTINELS = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "n.a.",
    "null",
    "none",
    "nil",
    "nan",
    "unknown",
    "unspecified",
    "tbd",
    "?",
    "#n/a",
    "#value!",
    "missing",
}

_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


class Quality(StrEnum):
    OK = "ok"
    MISSING = "missing"  # absent or sentinel -- legitimately unknown
    COERCED = "coerced"  # parsed, but the input needed interpretation
    OUT_OF_RANGE = "out_of_range"  # parsed but implausible -- treated as missing
    UNPARSEABLE = "unparseable"


@dataclass(frozen=True)
class Parsed:
    value: float | int | None
    quality: Quality
    note: str = ""

    @property
    def is_usable(self) -> bool:
        return self.value is not None and self.quality in (Quality.OK, Quality.COERCED)


def _clean(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bool):  # bools are ints in Python; never a metric
        return None
    text = str(raw).strip()
    if text.casefold() in _SENTINELS:
        return None
    return text


def _extract_number(text: str) -> float | None:
    """Pull a number out of a messy cell: '1,234', '40 hrs', '~8', '95%'."""
    candidate = text.replace(",", "") if re.search(r"\d,\d{3}\b", text) else text
    match = _NUMBER_RE.search(candidate)
    if not match:
        return None
    token = match.group(0).replace(",", ".")
    try:
        value = float(token)
    except ValueError:
        return None
    return None if math.isnan(value) or math.isinf(value) else value


def parse_count(raw, *, maximum: float = 100_000) -> Parsed:
    """Non-negative integer count (tasks, logins)."""
    text = _clean(raw)
    if text is None:
        return Parsed(None, Quality.MISSING, "absent or sentinel")
    number = _extract_number(text)
    if number is None:
        return Parsed(None, Quality.UNPARSEABLE, f"no number in {text!r}")
    if number < 0:
        return Parsed(None, Quality.OUT_OF_RANGE, "negative count")
    if number > maximum:
        return Parsed(None, Quality.OUT_OF_RANGE, f"exceeds {maximum:g}")
    quality = Quality.OK if text.strip().isdigit() else Quality.COERCED
    return Parsed(
        round(number), quality, "" if quality is Quality.OK else f"from {text!r}"
    )


def parse_hours(raw, *, maximum: float = 168.0) -> Parsed:
    """Duration in hours, tolerating minute/day-denominated inputs.

    A source switching from hours to minutes is a classic silent corruption:
    unconverted, '90' minutes reads as 90 hours of response latency and looks
    like catastrophic disengagement.
    """
    text = _clean(raw)
    if text is None:
        return Parsed(None, Quality.MISSING, "absent or sentinel")
    number = _extract_number(text)
    if number is None:
        return Parsed(None, Quality.UNPARSEABLE, f"no number in {text!r}")

    lowered = text.casefold()
    unit_note = ""
    if re.search(r"\b(m|min|mins|minute|minutes)\b", lowered) or lowered.endswith("m"):
        number, unit_note = number / 60.0, "converted from minutes"
    elif re.search(r"\b(s|sec|secs|second|seconds)\b", lowered):
        number, unit_note = number / 3600.0, "converted from seconds"
    elif re.search(r"\b(d|day|days)\b", lowered):
        number, unit_note = number * 24.0, "converted from days"

    if number < 0:
        return Parsed(None, Quality.OUT_OF_RANGE, "negative duration")
    if number > maximum:
        return Parsed(
            None,
            Quality.OUT_OF_RANGE,
            f"{number:g}h exceeds {maximum:g}h -- likely a unit mismatch",
        )
    quality = Quality.COERCED if (unit_note or not _looks_plain(text)) else Quality.OK
    return Parsed(
        round(number, 4),
        quality,
        unit_note or (f"from {text!r}" if quality is Quality.COERCED else ""),
    )


def _looks_plain(text: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", text.strip()))


def parse_week(raw) -> Parsed:
    from src.data_layer.ingestion import MAX_WEEK, MIN_WEEK

    text = _clean(raw)
    if text is None:
        return Parsed(None, Quality.MISSING, "absent or sentinel")
    number = _extract_number(text)
    if number is None:
        return Parsed(None, Quality.UNPARSEABLE, f"no number in {text!r}")
    week = round(number)
    if not MIN_WEEK <= week <= MAX_WEEK:
        return Parsed(None, Quality.OUT_OF_RANGE, f"outside {MIN_WEEK}-{MAX_WEEK}")
    return Parsed(week, Quality.OK)


def completeness(parsed_fields: dict[str, Parsed]) -> dict:
    """Summarise how much of a record actually arrived.

    Consumers use this to mark thin records low-confidence instead of scoring
    them as though they were complete -- the same principle the spec applies to
    cohort-relative fallbacks for employees with insufficient history.
    """
    total = len(parsed_fields) or 1
    usable = [k for k, p in parsed_fields.items() if p.is_usable]
    problems = {
        k: f"{p.quality.value}: {p.note}".strip(": ")
        for k, p in parsed_fields.items()
        if not p.is_usable
    }
    ratio = len(usable) / total
    return {
        "usable_fields": sorted(usable),
        "missing_or_invalid": problems,
        "completeness_ratio": round(ratio, 3),
        # Below half the metrics present, a personal deviation is noise.
        "low_confidence": ratio < 0.5,
    }
