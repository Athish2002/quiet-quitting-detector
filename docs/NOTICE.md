# What this system collects, and what it does with it

This is a plain-language notice. It is generated automatically from the system's own configuration, so it describes what the code actually does -- not what someone intended it to do.

## In one sentence

This system looks for changes in a few work-activity signals that might mean someone needs support, and prompts their manager to have a conversation -- it does not judge, rank, or score you for any decision about your job.

## What is collected

| What | Used to assess support needs? | Why | What else could explain it |
|---|---|---|---|
| `name` | No | Identity, required to route a briefing to the right manager conversation. | n/a -- identifier, not a behavioural signal. |
| `week_number` | No | Time index. Required for point-in-time correctness and trailing baselines. | n/a -- time index. |
| `tasks_completed` | Yes | Throughput relative to the individual's OWN trailing baseline. A sustained personal drop is a prompt to ask what changed. | Task size varies enormously. One large architectural task, a research spike, or a shift to mentoring/review work all reduce raw counts while contribution rises. |
| `avg_response_time` | Yes | Response latency drift vs the individual's own baseline; a cadence signal, not a productivity one. | Deep-focus work, timezone shifts, meeting-heavy weeks, or a deliberate move away from reactive interrupt-driven work all raise latency. |
| `weekly_hours` | Yes | Deviation from the individual's own norm, in EITHER direction -- a sustained rise is a burnout prompt, a sustained fall a disengagement prompt. | Approved part-time or compressed schedules, phased return from leave, public holidays, and caregiving arrangements all reduce hours legitimately. |
| `after_hours_logins` | Wellbeing only | Retained ONLY as a wellbeing/burnout indicator. Structurally barred from raising retention risk. | Non-US timezones, caregivers working after a school run, and personal preference for evening focus time all produce after-hours activity with zero disengagement meaning. |

The right-hand column matters. Every signal here has ordinary, innocent explanations, and the system is required to show them to your manager alongside anything it flags.

## What is deliberately NOT collected

The following are blocked at the point of collection. They are not stored, not inferred, and not reconstructed from anything else:

- Health, sickness, medical or leave-reason information
- The content or tone of your messages, email, or chat
- Keystrokes, mouse movement, screenshots, or webcam
- Your location or IP address
- Race, gender, age, religion, or similar characteristics
- Union membership, political or collective activity
- Anything about your life outside work
- Your salary or bonus amounts

Specific fields that were removed from an earlier version:

- `sick_days` -- HEALTH DATA. GDPR Art. 9 special category; ADA/FMLA discrimination exposure in the US. Using absence to raise a retention-risk score is indefensible.
- `sentiment` -- Provenance undocumented. If derived from message content this is an EU AI Act Art. 5 PROHIBITED practice (emotion inference in the workplace) -- banned outright, not merely high-risk. If it is a manager's manual tag it is the circular, bias-contaminated label problem instead.
- `task_accuracy` -- Performance/quality metric. Mixing performance into a retention-support tool is the fastest route to it being used punitively -- the exact failure mode this system is designed to prevent.

## What it is never used for

The system refuses these uses in code, not just in policy. A request naming one is rejected and recorded:

- bonus allocation
- compensation review
- disciplinary
- dismissal
- employee facing score display
- performance improvement plan
- pip
- promotion denial
- ranking
- redundancy selection
- stack ranking
- termination
- visa or immigration decision

Permitted uses are limited to:

- manager support conversation
- aggregate org health
- employee subject access
- model evaluation

## Who can see it

Your direct manager, for their own reports only, and only with a recorded reason for looking. There are no org-wide rankings and no cross-team 'at risk' lists. Every access is logged.

## How long it is kept

- raw events: 90 days (~3 months)
- features: 395 days (~13 months)
- scores: 395 days (~13 months)
- audit log: 2555 days (~84 months)

Deletion is real deletion, and it is tested.

## Your rights

You can ask for a copy of everything held about you, including the full log of who accessed it and why, and you can ask for it to be erased. Automated output is never the sole basis for a decision about you -- it exists to start a conversation, and a human being makes every call.

---

_Generated from `config/data_allowlist.json` (version 1). Do not edit by hand -- regenerate with `python -m src.governance.notice`._
