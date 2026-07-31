# Phase 0 — Legal exposure: go / no-go

**Status: GO for continued development on synthetic data. NO-GO for processing
any real employee's data without the conditions in §5 being met first.**

Written by engineering. **This is not legal advice.** It is an engineer's
assessment of where the exposure sits so counsel can be pointed at the right
questions. Nothing here substitutes for review by a qualified lawyer and, in
co-determination jurisdictions, by the works council.

---

## 1. Current scope (what makes this a GO today)

| Question | Answer |
|---|---|
| Real employee data? | **No.** 6 synthetic records, 4 weeks. |
| Real workforce? | **No.** Capstone/demo only. |
| Live employees in any jurisdiction? | **No.** |
| Historical exits usable as labels? | **None.** |
| Automated decisions affecting anyone? | **No.** |

Because no identifiable living person's data is processed, GDPR, the EU AI Act,
and US monitoring-notice statutes are **not currently engaged**. The exposure
below is what would attach the moment that changes — which is precisely why the
guardrails were built first rather than last.

---

## 2. What was fixed in Phase 0 (pre-existing violations)

These were live defects in the previous version, not hypotheticals:

| Issue | Severity | Resolution |
|---|---|---|
| `sick_days` ingested and used as a scored risk signal | **Critical** | Removed from schema, preprocessing, detector, and mock generator. Blocked by pattern-match at ingest. |
| `sentiment` ("Withdrawn") used as a signal, provenance undocumented | **Critical** | Removed. Blocked as `communication_content`. |
| `task_accuracy` (performance metric) feeding a support tool | High | Removed from risk scoring. |
| Absolute thresholds (`hours<30`, `after_hours>2`, `accuracy<85`) | High | Replaced with personal-deviation logic. |
| Real first names as storage keys | High | Pseudonymization required before real data (§5). |
| No record of who viewed whose score | High | Append-only audit log, DB-enforced immutability. |
| No purpose binding | High | Punitive purposes refused in code and audited. |
| No retention limits | Medium | TTLs enforced, real deletion, verified by test. |

**Why `sick_days` was the most serious.** It is health data — GDPR Art. 9
special category, requiring a separate lawful basis that an employer generally
cannot establish for retention scoring. Independently, using sickness absence to
raise a risk score is direct **ADA** (US) and **Equality Act 2010** (UK)
discrimination exposure, and interacts badly with **FMLA**-protected leave. It
was not a borderline call.

---

## 3. Regimes that attach when real data enters

### EU / EEA / UK

- **EU AI Act, Annex III(4)** — AI for worker management, task allocation, or
  evaluation is **high-risk**. Obligations: risk-management system, data
  governance, technical documentation, automatic logging, human oversight,
  accuracy/robustness testing, conformity assessment, and EU-database
  registration. Phase 0 covers logging and part of data governance; the rest is
  Phases 3–6 plus a compliance workstream that is **not** an engineering task.
- **EU AI Act, Art. 5(1)(f)** — inferring **emotions in the workplace** is a
  *prohibited* practice, not merely high-risk. This is why `sentiment` was
  removed outright rather than gated. It must not return without documented
  provenance proving it is neither content-derived nor an opinion label.
- **GDPR Art. 9** — health data. Addressed by removing `sick_days`.
- **GDPR Art. 35** — a **DPIA is mandatory** before processing. Systematic
  monitoring of employees at scale meets the threshold. This is a blocking
  prerequisite, not a formality.
- **GDPR Art. 22** — if output ever informs a decision with legal or similarly
  significant effect, Art. 22 safeguards apply. Purpose binding is designed to
  keep the system outside Art. 22 by refusing those uses structurally; that
  argument only holds if the refusals stay in place and are not bypassed.
- **GDPR Arts. 13–15** — transparency and subject access. `docs/NOTICE.md` and
  `export_subject_access_request()` are the artifacts.
- **Works councils (DE §87 BetrVG, NL, FR)** — monitoring systems are subject to
  **co-determination**. A works council can block deployment outright. Treat as
  a schedule risk, and engage before building further, not after.

### United States

- **Electronic monitoring notice** — NY Civil Rights Law §52-c, Connecticut, and
  Delaware require written notice. `after_hours_logins` is activity monitoring
  and triggers this even though it is now wellbeing-only.
- **ADA / FMLA** — addressed by removing `sick_days`. Do not reintroduce absence
  data in any form.
- **Caregiver / pregnancy discrimination** — the former absolute hours floor
  disproportionately flagged new parents and part-time workers. Fixed by moving
  to personal deviation; keep it that way.
- **Illinois BIPA** — not engaged (no biometrics), and must stay that way.

### Other

India, Canada (PIPEDA), and APAC regimes were **not** analysed. If employees are
located there, that analysis must happen before processing — I will not assume
they are permissive.

---

## 4. Residual risks not solved by code

1. **Proxy discrimination.** Removing protected attributes does not prevent it.
   Tenure, level, timezone, and hours all correlate with protected
   characteristics. Only measurement detects this — which requires the fairness
   evaluation in Phase 3, which requires labels we do not have.
2. **Function creep.** The single largest real-world risk. Purpose binding
   refuses forbidden uses at the API, but a determined operator with database
   access bypasses it. Mitigation is organisational, not technical.
3. **Chilling effects.** Employees who know activity is scored change behaviour.
   This is a harm to the workforce even when the system is accurate, and it is
   not measurable from inside the system.
4. **The label problem is unsolved** (Phase 3). Every candidate label carries
   bias; "manager-confirmed disengagement" in particular would teach the model
   which managers dislike which people.

---

## 5. Conditions before any real employee data

All of these are blocking:

1. Legal review by qualified counsel in **every** jurisdiction involved.
2. **DPIA completed** (GDPR Art. 35) where EU/UK employees exist.
3. **Works council consultation** concluded in DE/NL/FR.
4. **Pseudonymization implemented** — surrogate IDs at ingest, mapping table in a
   separate store with separate access control. Currently real first names are
   used as storage keys; this is a Phase 1 blocker.
5. **Employee notice served** (`docs/NOTICE.md`) before collection begins, not
   after.
6. **RBAC implemented** (Phase 5). There is presently **no authentication at
   all** — the API is fully open. Nothing goes near real data until this exists.
7. **Sentiment provenance documented** if anyone proposes reinstating it, plus
   explicit counsel sign-off against AI Act Art. 5.
8. **Fairness evaluation passing** its threshold (Phase 3), which presupposes
   enough labels to power it.

---

## 6. Recommendation

Proceed with Phases 1–2 on synthetic data. Treat Phase 3 as a **design document
plus a synthetic-data harness**, not a trained model — with 6 records and zero
exits, any reported metric would be meaningless, and a fairness claim we cannot
power is worse than no claim at all.

Revisit this document at the start of every phase, and rewrite it entirely
before the first real record is ingested.
