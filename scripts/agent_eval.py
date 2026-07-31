#!/usr/bin/env python
"""Golden eval suite for the agent logic (PRODUCTION_EVOLUTION_PROMPT.md 6.2, 8.9).

    uv run python scripts/agent_eval.py            # blocking: exit 1 on failure
    uv run python scripts/agent_eval.py --report   # report only, always exit 0

Runs `tests/eval/golden_set.json` through the REAL detection and scoring logic in
`src/domain`, with the deterministic fake scorer standing in for the LLM. No
network call is made, which is what allows this to be a blocking CI gate at all
(6.3: "CI must never call a real LLM").

Two kinds of case, and the distinction is the point:

  accuracy cases -- did we reach the right conclusion about this person
  safety cases   -- would the briefing have been safe to send

A system can pass every accuracy case and fail every safety case. Those failures
are the ones that hurt somebody, so a safety failure fails the whole suite
regardless of the accuracy score.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.domain import (
    FakeRiskScorer,
    WeekMetrics,
    confirm_signals,
)
from src.domain.critique import critique_briefing
from src.domain.models import Confidence

GOLDEN_SET = (
    pathlib.Path(__file__).resolve().parents[1] / "tests" / "eval" / "golden_set.json"
)

#: Accuracy cases that must pass for the suite to be green. Set to 100% on
#: purpose: every case here encodes a decision about a real person, and "we get
#: 8 of 9 right" is not a statement anyone would accept about which 1 it is.
REQUIRED_PASS_RATE = 1.0


def _weeks(rows: list[dict]) -> list[WeekMetrics]:
    return [WeekMetrics.model_validate(row) for row in rows]


def run_accuracy_case(case: dict) -> tuple[bool, list[str]]:
    """Detect and score one scenario, and check it against expectations."""
    timeline = _weeks(case["timeline"])
    signals = confirm_signals(timeline)
    assessment = FakeRiskScorer().score("Subject", signals, len(timeline), [], timeline)

    expect = case["expect"]
    failures: list[str] = []
    names = [s.signal_name for s in signals]

    if (
        "classification" in expect
        and assessment.classification != expect["classification"]
    ):
        failures.append(
            f"classification: expected {expect['classification']!r}, "
            f"got {assessment.classification!r} (score {assessment.score})"
        )

    if "min_score" in expect and assessment.score < expect["min_score"]:
        failures.append(
            f"score: expected >= {expect['min_score']}, got {assessment.score}"
        )

    if "signals" in expect and sorted(names) != sorted(expect["signals"]):
        failures.append(f"signals: expected {expect['signals']}, got {names}")

    for required in expect.get("signals_include", []):
        if required not in names:
            failures.append(
                f"signals: expected {required!r} to be present, got {names}"
            )

    if expect.get("all_signals_wellbeing_only"):
        offenders = [s.signal_name for s in signals if not s.wellbeing_only]
        if offenders:
            failures.append(
                f"wellbeing: {offenders} raised risk; these must never count against anyone"
            )
        if assessment.score != 1:
            failures.append(
                f"wellbeing: score rose to {assessment.score} on wellbeing signals alone"
            )

    if expect.get("low_confidence") and assessment.confidence not in (
        Confidence.LOW,
        Confidence.NONE,
    ):
        failures.append(
            f"confidence: expected low/none on thin evidence, got {assessment.confidence.value}"
        )

    return not failures, failures


def run_safety_case(case: dict) -> tuple[bool, list[str]]:
    """Put one drafted briefing in front of the critic."""
    try:
        confidence = Confidence(case.get("confidence", "moderate"))
    except ValueError:
        confidence = Confidence.MODERATE

    critique = critique_briefing(
        case["briefing"],
        first_name=case["first_name"],
        confirmed_signals=case.get("confirmed_signals", []),
        confidence=confidence,
        has_data_gap=case.get("has_data_gap", False),
    )

    found = {finding.value for finding in critique.findings}
    failures: list[str] = []

    if "must_block" in case:
        if case["must_block"] and not critique.must_block:
            failures.append(
                f"should have been blocked; critic found only {sorted(found)}"
            )
        if not case["must_block"] and critique.must_block:
            failures.append(f"blocked a safe briefing; critic found {sorted(found)}")

    for expected in case.get("must_flag", []):
        if expected not in found:
            failures.append(f"expected finding {expected!r}, got {sorted(found)}")

    if case.get("must_flag") == [] and "must_block" in case and not case["must_block"]:
        if found:
            failures.append(f"expected a clean briefing, got findings {sorted(found)}")

    return not failures, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="store_true",
        help="report results without failing the build",
    )
    args = parser.parse_args()

    data = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))

    print("=" * 74)
    print("AGENT EVAL -- golden set")
    print("=" * 74)

    accuracy_failures = 0
    print("\nAccuracy cases")
    for case in data["cases"]:
        passed, failures = run_accuracy_case(case)
        print(f"  [{'PASS' if passed else 'FAIL'}] {case['id']}")
        if not passed:
            accuracy_failures += 1
            print(f"         why it matters: {case['why']}")
            for failure in failures:
                print(f"         - {failure}")

    safety_failures = 0
    print("\nSafety cases")
    for case in data["safety_cases"]:
        passed, failures = run_safety_case(case)
        print(f"  [{'PASS' if passed else 'FAIL'}] {case['id']}")
        if not passed:
            safety_failures += 1
            print(f"         why it matters: {case['why']}")
            for failure in failures:
                print(f"         - {failure}")

    total_accuracy = len(data["cases"])
    total_safety = len(data["safety_cases"])
    pass_rate = (total_accuracy - accuracy_failures) / total_accuracy

    print("\n" + "-" * 74)
    print(
        f"Accuracy: {total_accuracy - accuracy_failures}/{total_accuracy} "
        f"({pass_rate:.0%})   Safety: {total_safety - safety_failures}/{total_safety}"
    )

    if safety_failures:
        print(
            "\nFAIL: a safety case failed. This is not traded off against the "
            "accuracy score -- a briefing that should not have been sent is not "
            "offset by getting other cases right."
        )
    elif pass_rate < REQUIRED_PASS_RATE:
        print(
            f"\nFAIL: accuracy {pass_rate:.0%} is below the {REQUIRED_PASS_RATE:.0%} gate."
        )
    else:
        print("\nOK: all accuracy and safety cases pass.")

    failed = bool(safety_failures) or pass_rate < REQUIRED_PASS_RATE
    if args.report and failed:
        print("(--report: not failing the build)")
        return 0
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
