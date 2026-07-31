# src/governance/notice.py
# Phase 0 -- the employee-facing notice, generated as a build artifact.
#
# Generated FROM config/data_allowlist.json rather than hand-written, because a
# hand-maintained notice drifts from the code the moment a field is added, and
# an inaccurate notice is worse than none: it is the document a regulator or an
# employee will hold you to.
#
# A test asserts the committed docs/NOTICE.md matches regenerated output, so
# changing the allowlist without regenerating fails the build.

from __future__ import annotations

import os

from src.governance.allowlist import load_policy
from src.governance.purpose import FORBIDDEN_PURPOSES, PermittedUse

NOTICE_PATH = os.path.join("docs", "NOTICE.md")


def generate_notice() -> str:
    policy = load_policy()
    permitted = policy["permitted_fields"]
    excluded = policy.get("excluded_fields", {})
    retention = policy.get("retention_days", {})

    lines: list[str] = []
    add = lines.append

    add("# What this system collects, and what it does with it")
    add("")
    add(
        "This is a plain-language notice. It is generated automatically from the "
        "system's own configuration, so it describes what the code actually does "
        "-- not what someone intended it to do."
    )
    add("")
    add("## In one sentence")
    add("")
    add(
        "This system looks for changes in a few work-activity signals that might "
        "mean someone needs support, and prompts their manager to have a "
        "conversation -- it does not judge, rank, or score you for any decision "
        "about your job."
    )
    add("")

    add("## What is collected")
    add("")
    add("| What | Used to assess support needs? | Why | What else could explain it |")
    add("|---|---|---|---|")
    for name, spec in permitted.items():
        used = "Yes" if spec.get("risk_scoring") else "No"
        if spec.get("wellbeing_only"):
            used = "Wellbeing only"
        add(
            f"| `{name}` | {used} | {spec.get('rationale', '--')} | "
            f"{spec.get('benign_explanation', '--')} |"
        )
    add("")
    add(
        "The right-hand column matters. Every signal here has ordinary, "
        "innocent explanations, and the system is required to show them to your "
        "manager alongside anything it flags."
    )
    add("")

    add("## What is deliberately NOT collected")
    add("")
    add(
        "The following are blocked at the point of collection. They are not "
        "stored, not inferred, and not reconstructed from anything else:"
    )
    add("")
    categories = policy.get("forbidden_patterns", {})
    friendly = {
        "health": "Health, sickness, medical or leave-reason information",
        "communication_content": "The content or tone of your messages, email, or chat",
        "telemetry": "Keystrokes, mouse movement, screenshots, or webcam",
        "location": "Your location or IP address",
        "protected_characteristics": "Race, gender, age, religion, or similar characteristics",
        "collective_and_political": "Union membership, political or collective activity",
        "personal_life": "Anything about your life outside work",
        "compensation": "Your salary or bonus amounts",
    }
    for key in categories:
        if key.startswith("$"):
            continue
        add(f"- {friendly.get(key, key.replace('_', ' ').title())}")
    add("")
    if excluded:
        add("Specific fields that were removed from an earlier version:")
        add("")
        for name, spec in excluded.items():
            add(f"- `{name}` -- {spec.get('reason', '')}")
        add("")

    add("## What it is never used for")
    add("")
    add(
        "The system refuses these uses in code, not just in policy. A request "
        "naming one is rejected and recorded:"
    )
    add("")
    for purpose in sorted(FORBIDDEN_PURPOSES):
        add(f"- {purpose.replace('_', ' ')}")
    add("")
    add("Permitted uses are limited to:")
    add("")
    for use in PermittedUse.__members__.values():
        add(f"- {use.value.replace('_', ' ')}")
    add("")

    add("## Who can see it")
    add("")
    add(
        "Your direct manager, for their own reports only, and only with a "
        "recorded reason for looking. There are no org-wide rankings and no "
        "cross-team 'at risk' lists. Every access is logged."
    )
    add("")

    add("## How long it is kept")
    add("")
    for bucket, days in retention.items():
        if bucket.startswith("$"):
            continue
        label = bucket.replace("_", " ")
        add(f"- {label}: {days} days (~{round(int(days) / 30.4)} months)")
    add("")
    add("Deletion is real deletion, and it is tested.")
    add("")

    add("## Your rights")
    add("")
    add(
        "You can ask for a copy of everything held about you, including the full "
        "log of who accessed it and why, and you can ask for it to be erased. "
        "Automated output is never the sole basis for a decision about you -- it "
        "exists to start a conversation, and a human being makes every call."
    )
    add("")
    add("---")
    add("")
    add(
        f"_Generated from `config/data_allowlist.json` (version "
        f"{policy.get('version', '?')}). Do not edit by hand -- regenerate with "
        "`python -m src.governance.notice`._"
    )
    add("")
    return "\n".join(lines)


def write_notice(path: str = NOTICE_PATH) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    content = generate_notice()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return path


if __name__ == "__main__":
    print(f"Wrote {write_notice()}")
