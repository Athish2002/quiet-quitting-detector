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

load_dotenv(override=True)
if "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

# ---------------------------------------------------------------------------
# Force UTF-8 stdout so Unicode characters don't crash on Windows cp1252
# ---------------------------------------------------------------------------
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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

    employee_records: dict[str, list[dict]] = {}
    max_week = 0

    for file_path in csv_files:
        filename = os.path.basename(file_path)
        try:
            name_part = os.path.splitext(filename)[0]
            week_num = int("".join(filter(str.isdigit, name_part)))
        except ValueError:
            week_num = 1
        max_week = max(max_week, week_num)

        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_name = (
                    row.get("employee_name")
                    or row.get("name")
                    or row.get("first_name")
                    or "Unknown"
                )
                first_name = raw_name.split()[0]

                # Safely parse metrics directly
                completed_tasks = 0
                try:
                    val = row.get("tasks_completed") or row.get("completed_tasks")
                    if val:
                        completed_tasks = int(val)
                except ValueError:
                    pass

                response_time = 0.0
                try:
                    val = row.get("avg_response_time_hours") or row.get("response_time")
                    if val:
                        response_time = float(val)
                except ValueError:
                    pass

                after_hours_logins = 0
                try:
                    val = row.get("after_hours_logins")
                    if val:
                        after_hours_logins = int(val)
                except ValueError:
                    pass

                sick_days = 0
                try:
                    val = row.get("sick_days")
                    if val:
                        sick_days = int(val)
                except ValueError:
                    pass

                metrics = {
                    "week": week_num,
                    "completed_tasks": completed_tasks,
                    "response_time": response_time,
                    "after_hours_logins": after_hours_logins,
                    "sick_days": sick_days,
                }
                employee_records.setdefault(first_name, []).append(metrics)

    return employee_records, max_week


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
        expected_weeks = set(range(1, max_week + 1))
        expected_weeks - processed_weeks

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
                        "sick_days": None,
                        "data_missing": True,
                    }
                )

        print()
        print("  Weekly data timeline:")
        for rec in full_timeline:
            if rec.get("data_missing"):
                print(f"    Week {rec['week']}: [DATA MISSING]")
            else:
                print(
                    f"    Week {rec['week']}: tasks={rec['completed_tasks']:>2}  "
                    f"response={rec['response_time']:.2f}h  "
                    f"after_hours={rec['after_hours_logins']}  "
                    f"sick={rec['sick_days']}"
                )

        # ==================================================================
        # Chronological Simulation (Week 1 -> Max Week)
        # ==================================================================
        print()
        print("  Running agent evaluation chronologically week-by-week:")
        signals = []
        risk_data = {}

        for w in range(1, max_week + 1):
            sub_timeline = [rec for rec in full_timeline if rec["week"] <= w]
            print(f"    --- Simulating Week {w} ---")

            # 1. Trend Detector Agent
            try:
                signals = detect_trends(first_name, sub_timeline)
            except Exception:
                signals = []

            # 2. Risk Scorer Agent (save current week memory)
            try:
                risk_data = score_risk(first_name, signals, w)
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
        briefing = ""
        if classification in FLAGGED:
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
    run()
