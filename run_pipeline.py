"""
run_pipeline.py -- Quiet-Quitting Detector end-to-end runner.

Processes all 4 weekly CSV files through the full agent pipeline,
prints labelled per-agent output as it runs, then writes a final
engagement_report.txt to the project root.

Usage:
    uv run python run_pipeline.py
"""

import csv
import glob
import io
import json
import logging
import os
import sys
import textwrap
from datetime import datetime

from dotenv import load_dotenv

from src.data_layer.ingestion import parse_week_number
from src.data_layer.preprocessing import preprocess_employee_records

load_dotenv(override=True)
if "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


def _force_utf8_stdio() -> None:
    """Force UTF-8 stdout so Unicode doesn't crash on Windows cp1252.

    Called from __main__ only. Doing this at import time replaced the streams
    for anything that merely imported this module -- which broke pytest's
    output capture, and is a side effect no import should have.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            setattr(
                sys, name, io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")
            )


# ---------------------------------------------------------------------------
# Silence chatty library loggers -- keep only our own INFO+ output.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)

DIVIDER_THICK = "=" * 72
DIVIDER_THIN = "-" * 72
FLAGGED = {"Watch", "At Risk", "Silent Exit"}
BADGE = {
    "Healthy": "[HEALTHY]",
    "Watch": "[WATCH]",
    "At Risk": "[AT RISK]",
    "Silent Exit": "[SILENT EXIT]",
}


def _banner(text: str) -> None:
    print()
    print(DIVIDER_THICK)
    print(f"  {text}")
    print(DIVIDER_THICK)


def _section(label: str) -> None:
    print()
    print(DIVIDER_THIN)
    print(f"  {label}")
    print(DIVIDER_THIN)


def _indent(text: str, width: int = 4) -> str:
    prefix = " " * width
    return "\n".join(prefix + line for line in str(text).splitlines())


# ---------------------------------------------------------------------------
# Low-level CSV reader
# ---------------------------------------------------------------------------
def _load_all_weeks(weekly_folder: str = "data/weekly") -> tuple[dict, int]:
    """Return (employee_records, max_week)."""
    if not os.path.exists(weekly_folder):
        print(f"[ERROR] Data folder '{weekly_folder}' not found.")
        sys.exit(1)

    csv_files = sorted(glob.glob(os.path.join(weekly_folder, "*.csv")))
    if not csv_files:
        print("[ERROR] No CSV files found in data/weekly/")
        sys.exit(1)

    # Delegates to the SAME preprocessing the API path uses. This entrypoint
    # previously carried its own inline copy of the parsing, which meant every
    # governance control -- the default-deny allowlist, identity resolution and
    # missing-value semantics -- applied only to `app.py`. Concretely, the
    # duplicate still read `sick_days` (health data, prohibited by
    # config/data_allowlist.json and CONTEXT.md rule 6), still keyed records on
    # first name (merging distinct people and splitting one person across
    # spelling variants), and still defaulted an absent metric to 0, which is
    # indistinguishable from total disengagement.
    #
    # One shared path is the only way those controls hold: a second copy is a
    # second place for them to silently not apply.
    raw_rows: list[dict] = []
    max_week = 0

    for file_path in csv_files:
        week_num = parse_week_number(os.path.basename(file_path))
        max_week = max(max_week, week_num)
        with open(file_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row["__week_number__"] = week_num
                row["__source_file__"] = os.path.basename(file_path)
                raw_rows.append(row)

    employee_records, detected_max = preprocess_employee_records(raw_rows)
    return employee_records, max(max_week, detected_max)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------
def run() -> None:
    _banner("QUIET-QUITTING DETECTOR  |  Full End-to-End Pipeline Run")
    print(f"  Run started : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"  API Key loaded: {os.environ.get('GEMINI_API_KEY', '')[:12]}...")

    # Import agent functions after env is set up.
    from src.manager_briefing_agent import (
        _SAFE_FALLBACK_BRIEFING,
        generate_briefing,
    )
    from src.risk_scorer_agent import score_risk
    from src.trend_detector_agent import detect_trends

    # -----------------------------------------------------------------------
    # Step 0 -- Load all CSV weeks
    # -----------------------------------------------------------------------
    _banner("STEP 0 -- Loading CSV Files")
    employee_records, max_week = _load_all_weeks()
    print(f"  Weeks found  : {max_week}")
    print(f"  Employees    : {sorted(employee_records.keys())}")

    all_results: dict[str, dict] = {}

    # -----------------------------------------------------------------------
    # Process each employee through the full 3-agent chain
    # -----------------------------------------------------------------------
    for first_name in sorted(employee_records.keys()):
        weeks_data = sorted(employee_records[first_name], key=lambda x: x["week"])

        _banner(f"EMPLOYEE: {first_name}")

        # -- Build full timeline with gap markers --
        processed_weeks = {w["week"] for w in weeks_data}

        full_timeline: list[dict] = []
        for w in range(1, max_week + 1):
            if w in processed_weeks:
                rec = next(r for r in weeks_data if r["week"] == w)
                full_timeline.append(rec)
            else:
                full_timeline.append(
                    {
                        "week": w,
                        "completed_tasks": None,
                        "response_time": None,
                        "after_hours_logins": None,
                        "weekly_hours": None,
                        "data_missing": True,
                    }
                )

        print()
        print("  Weekly data timeline:")
        for rec in full_timeline:
            if rec.get("data_missing"):
                print(f"    Week {rec['week']}: [DATA MISSING]")
            else:
                # Metrics are Optional now: an absent value stays None rather
                # than being defaulted to 0, so it must render as "n/a" instead
                # of crashing the format spec -- and, more importantly, instead
                # of being displayed as a real zero.
                def _fmt(value, spec: str = "") -> str:
                    return "n/a" if value is None else format(value, spec)

                print(
                    f"    Week {rec['week']}: tasks={_fmt(rec['completed_tasks'], '>2')}  "
                    f"response={_fmt(rec['response_time'], '.2f')}h  "
                    f"after_hours={_fmt(rec['after_hours_logins'])}"
                )

        # ==================================================================
        # Chronological Simulation (Week 1 -> Max Week)
        # ==================================================================
        print()
        print("  Running agent evaluation chronologically week-by-week:")
        memory_dir = os.path.join("data", "memory")
        signals = []
        risk_data = {}
        briefing = ""
        final_week_cached = False

        for w in range(1, max_week + 1):
            sub_timeline = [rec for rec in full_timeline if rec["week"] <= w]
            memory_file_path = os.path.join(
                memory_dir, f"{first_name.lower()}_week{w}.json"
            )

            # Reuse a previous run's evaluation instead of re-calling the
            # agents. Without this, every run re-scored every week from
            # scratch even when nothing about that week had changed --
            # by far the largest avoidable source of Gemini API calls,
            # since a typical 4-week re-run only ever has one truly new week.
            cached = None
            if os.path.exists(memory_file_path):
                try:
                    with open(memory_file_path, encoding="utf-8") as f:
                        candidate = json.load(f)
                    if {"score", "classification", "rationale"} <= candidate.keys():
                        cached = candidate
                except Exception:
                    cached = None

            if cached is not None:
                print(f"    --- Week {w}: reusing cached evaluation (no API calls) ---")
                signals = cached.get("signals", [])
                risk_data = cached
                briefing = cached.get("briefing", "")
                final_week_cached = w == max_week
                continue

            print(f"    --- Simulating Week {w} ---")
            final_week_cached = False
            briefing = ""

            # 1. Trend Detector Agent
            try:
                signals = detect_trends(first_name, sub_timeline)
            except Exception:
                signals = []

            # 2. Risk Scorer Agent (save current week memory)
            try:
                risk_data = score_risk(first_name, signals, w, timeline=sub_timeline)
            except Exception:
                risk_data = {
                    "score": 4,
                    "classification": "Watch",
                    "rationale": f"Scoring unavailable due to error in week {w}.",
                    "healthy_streak": 0,
                }

        # Show final (max_week) trend detection results
        _section(f"AGENT 1 > Trend Detector  [{first_name}]")
        if signals:
            for sig in signals:
                sev = sig.get("severity", "?").upper()
                sname = sig.get("signal_name") or sig.get("signal", "Unknown")
                weeks = sig.get("weeks_detected", [])
                details = sig.get("details", "")
                wk_str = f"  (weeks {weeks})" if weeks else ""
                print(f"  >> [{sev:<6}] {sname}{wk_str}")
                if details:
                    print(f"           {str(details)[:120]}")
        else:
            print("  [OK] No persistent disengagement signals detected.")

        # Show final (max_week) risk scoring results
        _section(f"AGENT 2 > Risk Scorer  [{first_name}]")
        score = risk_data.get("score", "?")
        classification = risk_data.get("classification", "Unknown")
        rationale = risk_data.get("rationale", "")
        badge = BADGE.get(classification, "[UNKNOWN]")

        print(f"  {badge}  Score: {score}/10   Classification: {classification}")
        print()
        print("  Rationale:")
        print(
            textwrap.fill(
                str(rationale),
                width=68,
                initial_indent="    ",
                subsequent_indent="    ",
            )
        )

        # ==================================================================
        # AGENT 3 -- Manager Briefing (flagged employees only)
        # ==================================================================
        if final_week_cached:
            # Week was reused from a previous run's memory file -- avoid a
            # second unnecessary API call by reusing its stored briefing too.
            _section(f"AGENT 3 > Manager Briefing  [{first_name}]")
            if classification in FLAGGED:
                if briefing:
                    print("  [OK] Reusing cached briefing (no API call).")
                    print()
                    print(_indent(briefing, 2))
                else:
                    print(
                        "  Cached record is missing a briefing -- generating it once..."
                    )
                    try:
                        briefing = generate_briefing(first_name, signals, risk_data)
                    except Exception:
                        briefing = _SAFE_FALLBACK_BRIEFING
                    print()
                    print(_indent(briefing, 2))
            else:
                print(f"  [OK] Skipped -- {first_name} is classified as Healthy.")
        elif classification in FLAGGED:
            _section(f"AGENT 3 > Manager Briefing  [{first_name}]")
            print("  Calling manager_briefing_agent ...")
            try:
                briefing = generate_briefing(first_name, signals, risk_data)
            except Exception:
                print(
                    "  [WARN] Briefing agent raised an exception -- using safe fallback."
                )
                briefing = _SAFE_FALLBACK_BRIEFING
            print()
            print(_indent(briefing, 2))
        else:
            _section(f"AGENT 3 > Manager Briefing  [{first_name}]")
            print(f"  [OK] Skipped -- {first_name} is classified as Healthy.")

        # Persist the briefing into the same memory JSON file score_risk() just
        # wrote for the final week. score_risk() only knows about the risk
        # score/signals at save time -- the briefing is generated afterward in
        # this script and, without this, was only ever shown in the CLI's own
        # printed report and never reached data/memory/*.json. That's what the
        # web UI reads, so briefings generated by this script silently never
        # appeared there.
        if briefing:
            memory_file_path = os.path.join(
                "data", "memory", f"{first_name.lower()}_week{max_week}.json"
            )
            try:
                with open(memory_file_path, encoding="utf-8") as f:
                    saved_risk_data = json.load(f)
                saved_risk_data["briefing"] = briefing
                with open(memory_file_path, "w", encoding="utf-8") as f:
                    json.dump(saved_risk_data, f, indent=2)
            except Exception:
                pass  # best-effort; the CLI report above already shows the briefing

        all_results[first_name] = {
            "signals": signals,
            "risk_data": risk_data,
            "briefing": briefing or "No briefing required (Healthy status).",
        }

    # -----------------------------------------------------------------------
    # TEAM SUMMARY
    # -----------------------------------------------------------------------
    _banner("TEAM SUMMARY -- All 6 Employees")
    print()
    print(f"  {'Employee':<12} {'Score':>5}  {'Classification':<14}  Signals")
    print(f"  {'-' * 12} {'-' * 5}  {'-' * 14}  {'-' * 35}")
    for name in sorted(all_results):
        rd = all_results[name]["risk_data"]
        sigs = all_results[name]["signals"]
        sig_names = [
            (s.get("signal_name") or s.get("signal", ""))
            for s in sigs
            if (s.get("signal_name") or s.get("signal", "")) != "MISSING_DATA_GAP"
        ]
        badge = BADGE.get(rd.get("classification", ""), "[?]")
        sig_str = ", ".join(sig_names) if sig_names else "None"
        print(f"  {name:<12} {rd.get('score', '?'):>5}  {badge:<14}  {sig_str[:50]}")

    # -----------------------------------------------------------------------
    # INDIVIDUAL RISK CARDS (flagged employees only)
    # -----------------------------------------------------------------------
    _banner("INDIVIDUAL RISK CARDS -- Flagged Employees")
    for name in ["Arjun", "Priya", "Karthik", "Meena"]:
        if name not in all_results:
            print(f"\n  [SKIP] {name} not in results.")
            continue
        rd = all_results[name]["risk_data"]
        sigs = all_results[name]["signals"]
        badge = BADGE.get(rd.get("classification", ""), "[?]")
        print()
        print(f"  +-- RISK CARD: {name} {'--' * 28}")
        print(f"  |  Score          : {rd.get('score')}/10")
        print(f"  |  Classification : {badge} {rd.get('classification')}")
        rationale_line = str(rd.get("rationale", ""))[:90]
        print(f"  |  Rationale      : {rationale_line}")
        print("  |  Signals Detected:")
        for sig in sigs:
            sname = sig.get("signal_name") or sig.get("signal", "Unknown")
            sev = sig.get("severity", "?")
            if sname == "MISSING_DATA_GAP":
                continue
            print(f"  |    * [{sev}] {sname}")
        print(f"  +{'--' * 36}")

    # -----------------------------------------------------------------------
    # MEMORY FILE CONFIRMATION
    # -----------------------------------------------------------------------
    _banner("MEMORY FILE CONFIRMATION -- data\\memory\\")
    memory_dir = os.path.join("data", "memory")
    json_files = [
        f
        for f in glob.glob(os.path.join(memory_dir, "*.json"))
        if os.path.basename(f) != ".gitkeep"
    ]
    if json_files:
        for jf in sorted(json_files):
            fname = os.path.basename(jf)
            try:
                with open(jf, encoding="utf-8") as f:
                    data = json.load(f)
                print(
                    f"  [OK] {fname:<35}  score={data.get('score')}  "
                    f"class={data.get('classification')}"
                )
            except Exception:
                print(f"  [ERR] {fname} -- could not read")
    else:
        print("  [WARN] No memory JSON files found in data/memory/")

    # -----------------------------------------------------------------------
    # ARJUN BRIEFING CONTENT CHECK
    # -----------------------------------------------------------------------
    _banner("ARJUN BRIEFING -- Content Check (Silent Exit)")
    arjun_briefing = all_results.get("Arjun", {}).get("briefing", "")
    if arjun_briefing and arjun_briefing != "No briefing required (Healthy status).":
        print()
        print(_indent(arjun_briefing, 2))
        print()
        briefing_lower = arjun_briefing.lower()
        checks = {
            "Evidence-Based Actions section": any(
                phrase in briefing_lower
                for phrase in [
                    "evidence-based actions",
                    "evidence based actions",
                    "actions",
                ]
            ),
            "Supportive guidance (things to say)": any(
                phrase in briefing_lower
                for phrase in ["things to say", "supportive", "1-on-1", "one-on-one"]
            ),
            "Pre-Meeting Observation": "pre-meeting" in briefing_lower
            or "observation" in briefing_lower,
            "Things Never to Say": "never to say" in briefing_lower
            or "never say" in briefing_lower,
        }
        print("  Briefing section checks:")
        for check, found in checks.items():
            status = "[FOUND]" if found else "[MISSING]"
            print(f"    {status}  {check}")
    else:
        print("  [INFO] No briefing generated for Arjun.")

    # -----------------------------------------------------------------------
    # Build and save full report
    # -----------------------------------------------------------------------
    report_lines: list[str] = []

    def _rpt(*args):
        report_lines.append(" ".join(str(a) for a in args))

    _rpt(DIVIDER_THICK)
    _rpt("QUIET-QUITTING DETECTOR -- ENGAGEMENT REPORT")
    _rpt(f"Generated: {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    _rpt(DIVIDER_THICK)
    _rpt()
    _rpt("TEAM SUMMARY")
    _rpt(DIVIDER_THIN)
    _rpt(f"{'Employee':<12} {'Score':>5}  {'Classification':<14}  Signals")
    _rpt(f"{'-' * 12} {'-' * 5}  {'-' * 14}  {'-' * 40}")
    for name in sorted(all_results):
        rd = all_results[name]["risk_data"]
        sigs = all_results[name]["signals"]
        sig_names = [
            (s.get("signal_name") or s.get("signal", ""))
            for s in sigs
            if (s.get("signal_name") or s.get("signal", "")) != "MISSING_DATA_GAP"
        ]
        _rpt(
            f"{name:<12} {rd.get('score', '?'):>5}  "
            f"{rd.get('classification', ''):<14}  "
            f"{', '.join(sig_names) if sig_names else 'None'}"
        )

    _rpt()
    _rpt(DIVIDER_THIN)
    _rpt("INDIVIDUAL RISK CARDS (Flagged Employees)")
    _rpt(DIVIDER_THIN)
    for name in ["Arjun", "Priya", "Karthik", "Meena"]:
        if name not in all_results:
            continue
        rd = all_results[name]["risk_data"]
        sigs = all_results[name]["signals"]
        _rpt()
        _rpt(f"Employee      : {name}")
        _rpt(f"Score         : {rd.get('score')}/10")
        _rpt(f"Classification: {rd.get('classification')}")
        _rpt(f"Rationale     : {rd.get('rationale', '')}")
        _rpt("Signals:")
        for sig in sigs:
            sname = sig.get("signal_name") or sig.get("signal", "Unknown")
            sev = sig.get("severity", "?")
            if sname == "MISSING_DATA_GAP":
                continue
            _rpt(f"  [{sev}] {sname}")
        _rpt()
        _rpt("Manager Briefing:")
        _rpt(all_results[name].get("briefing", "N/A"))
        _rpt(DIVIDER_THIN)

    _rpt()
    _rpt("MEMORY FILES SAVED")
    _rpt(DIVIDER_THIN)
    for jf in sorted(glob.glob(os.path.join("data", "memory", "*.json"))):
        fname = os.path.basename(jf)
        if fname == ".gitkeep":
            continue
        try:
            with open(jf, encoding="utf-8") as f:
                data = json.load(f)
            _rpt(
                f"{fname:<35}  score={data.get('score')}  "
                f"class={data.get('classification')}"
            )
        except Exception:
            _rpt(f"{fname} -- unreadable")

    report_text = "\n".join(report_lines)
    report_path = "engagement_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    _banner("PIPELINE COMPLETE")
    print(f"  Full report saved to: {os.path.abspath(report_path)}")
    print()


if __name__ == "__main__":
    _force_utf8_stdio()
    run()
