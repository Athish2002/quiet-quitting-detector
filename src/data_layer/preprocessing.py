# src/data_layer/preprocessing.py
# Preprocessing layer for grouping, converting metrics, and timeline baseline formatting.

import logging

from src.data_layer.coercion import completeness, parse_count, parse_hours
from src.data_layer.identity import get_resolver
from src.data_layer.ingestion import COLUMN_ALIASES, resolve_header_value

logger = logging.getLogger(__name__)


def preprocess_employee_records(
    raw_rows: list[dict],
    *,
    key_by_surrogate: bool = False,
) -> tuple[dict[str, list[dict]], int]:
    """Group rows per person, parse metrics tolerantly, and find the max week.

    Grouping goes through the identity resolver rather than the raw first name.
    Keying on a first name both merged distinct people ("Arjun Sharma" and
    "Arjun Patel" -> one blended timeline) and split one person across casing
    variants -- so baselines were computed over the wrong rows in both
    directions.

    Args:
        key_by_surrogate: key the result by pseudonymous surrogate ID instead of
            display name. Required before real personal data is processed
            (Phase 0); defaults to False so existing callers and the demo UI are
            unaffected.
    """
    employee_records: dict[str, list[dict]] = {}
    max_week = 0
    resolver = get_resolver()

    for row in raw_rows:
        week_num = row.get("__week_number__", 1)
        max_week = max(max_week, week_num)

        identity = resolver.resolve(row)
        group_key = identity.surrogate_id if key_by_surrogate else identity.display_name

        # Tolerant parsing. Absent/sentinel values stay None: defaulting a
        # missing task count to 0 fabricates the exact signal (total
        # disengagement) this system exists to detect.
        parsed = {
            "completed_tasks": parse_count(
                resolve_header_value(row, COLUMN_ALIASES["tasks_completed"], "")
            ),
            "response_time": parse_hours(
                resolve_header_value(row, COLUMN_ALIASES["avg_response_time"], "")
            ),
            "after_hours_logins": parse_count(
                resolve_header_value(row, COLUMN_ALIASES["after_hours_logins"], "")
            ),
            "weekly_hours": parse_hours(
                resolve_header_value(row, COLUMN_ALIASES["weekly_hours"], "")
            ),
        }

        for field_name, result in parsed.items():
            if result.quality.value in ("unparseable", "out_of_range"):
                logger.warning(
                    "Week %s: unusable %s (%s) -- treated as missing, not zero.",
                    week_num,
                    field_name,
                    result.note,
                )

        quality = completeness(parsed)

        # sick_days / task_accuracy / sentiment are intentionally absent: they
        # are prohibited by config/data_allowlist.json (health data, performance
        # metric, and emotion inference respectively) and are dropped at the
        # ingest boundary. Legacy CSVs may still carry the columns; they are
        # simply not read.
        metrics = {
            "week": week_num,
            "completed_tasks": parsed["completed_tasks"].value,
            "response_time": parsed["response_time"].value,
            "after_hours_logins": parsed["after_hours_logins"].value,
            "weekly_hours": parsed["weekly_hours"].value,
            "source_file": row.get("__source_file__", ""),
            # Carried so scoring can flag thin records low-confidence rather
            # than presenting a deviation computed from almost no data.
            "data_quality": quality,
            "surrogate_id": identity.surrogate_id,
            "identity_source": identity.key_source,
            "identity_ambiguous": identity.is_ambiguous,
        }
        if quality["low_confidence"]:
            logger.info(
                "Week %s for %s is %.0f%% complete -- flagged low confidence.",
                week_num,
                identity.display_name,
                quality["completeness_ratio"] * 100,
            )

        if group_key not in employee_records:
            employee_records[group_key] = []
        employee_records[group_key].append(metrics)

    # Sort each employee's week records chronologically
    for key in employee_records:
        employee_records[key].sort(key=lambda x: x["week"])

    return employee_records, max_week
