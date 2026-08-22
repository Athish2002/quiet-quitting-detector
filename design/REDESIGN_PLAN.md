# Frontend Redesign — Session Plan

Source: `design/design_handoff_qq_ui/` (unzipped 2026-08-22).
Format follows `SESSION_PLAYBOOK.md`: one session = one task = one commit, files named up front,
explicit exit criterion. Read `PROGRESS.md` first, update it last, every session.

---

## Scope

The handoff replaces four sibling pages (`Home`, `Console`, `DiagnosticRoom`, `History`) with
**one app shell + eight sections**. The visual language is a total reset: Modernist flat —
`border-radius: 0` everywhere, **no shadows at all**, elevation carried entirely by 1px/2px rules
and fills. The current frontend is glassmorphism (gradients, blur, shadows, rounded corners), so
almost nothing in `styles.css` survives.

Three of the eight sections are new surfaces over governance code that already exists in
`src/governance/` but was never exposed over HTTP.

---

## Decisions taken before session 1

### 1. Dark mode is IN scope — this departs from the handoff

The handoff assumes a single committed light palette and specifies no dark mode. Keeping the
existing `ThemeToggle` is a deliberate override.

The cost is real, and is the reason this is decided up front rather than discovered in session 6:
the handoff's **rule 8** requires every classification band to clear 4.5:1 against its paired
background. Those four pairs are verified for *light* only. A dark theme needs a second verified
set, or the toggle silently voids the accessibility guarantee the design is built on.

That set is derived and verified below. It is not a guess.

`ThemeToggle.tsx` is kept as-is — its `data-theme-switching` fix for the `var()`-transition freeze
is correct and hard-won. It moves into the sidebar footer block, below the
"Local scoring · model qq-local-2.3" line, restyled as a Modernist secondary button.

### 2. The retention grid is generated from config, never typed from the mockup

The mockup's retention grid **contradicts** `config/data_allowlist.json`, which `CLAUDE.md` rule 6
makes the source of truth:

| Mockup row | Mockup says | `data_allowlist.json` says |
| --- | --- | --- |
| Raw weekly rows | 90 days | `raw_events: 90` — agrees |
| Derived assessments | 180 days | `features`/`scores: 395` — **contradicts** |
| Access trail | 7 years | `audit_log: 2555` — agrees |
| Manager verdicts | 2 years | no bucket exists |
| Simulator scratch | session | no bucket exists |
| Refused requests | 2 years | no bucket exists |

Hardcoding the mockup's numbers would put a false retention promise in front of employees and
drift from `docs/NOTICE.md`, which is generated from the same file. **Section 8 renders whatever
the config holds.** Adding the three missing buckets is a config decision, not a UI decision —
see the open question at the end.

### 3. Verified dark palette

Neutrals. Dark `--rule` is tuned to match the light-mode rule/ground *relationship* (light is only
1.30:1 on paper, 1.42:1 on surface) — not to 3:1, which would make dark-mode rules far heavier
than the design intends.

| Token | Light | Dark | Dark check |
| --- | --- | --- | --- |
| `--paper` | `#F2F5F4` | `#121817` | — |
| `--surface` | `#FFFFFF` | `#1B2422` | — |
| `--ink` | `#1B2422` | `#F2F5F4` | 16.38:1 on paper, 14.48:1 on surface |
| `--muted` | `#5A6A66` | `#9DACA8` | 7.62:1 on paper, 6.73:1 on surface |
| `--rule` | `#D2DAD7` | `#323E3B` | 1.62:1 / 1.43:1 — matches light's 1.30 / 1.42 |
| `--accent` | `#1D4E6B` | `#7FB6D6` | 8.18:1 on paper, 7.23:1 on surface |
| `--accent-bg` | `#EAF1F5` | `#1A2C38` | ink 13.10:1, accent 6.55:1 on it |

Classification bands, dark. All four clear 4.5:1 on their own chip **and** on both dark neutrals,
so a band-coloured trajectory label is safe anywhere.

| Band | Dark fg | Dark bg | On chip | On paper | On surface |
| --- | --- | --- | --- | --- | --- |
| Healthy | `#44A769` | `#152119` | 5.52:1 | 5.97:1 | 5.28:1 |
| Watch | `#B19148` | `#211D15` | 5.60:1 | 6.00:1 | 5.30:1 |
| At Risk | `#C18267` | `#211815` | 5.52:1 | 5.70:1 | 5.03:1 |
| Silent Exit | `#C58072` | `#211715` | 5.60:1 | 5.74:1 | 5.07:1 |

**Correction to the handoff's own figures.** Recomputed under WCAG 2.x, light-mode Healthy is
**4.53:1, not the 4.59:1 stated** (Silent Exit is 7.25, not 7.29; Watch and At Risk match to 0.01).
Healthy therefore has **0.03 of headroom** over the 4.5 floor. Do not retune it without re-running
the check.

---

## Sessions

Ordering rule: S1 is additive (nothing changes visually), S2 cuts the shell over, S3–S9 bring one
section each to final, S10–S11 add the one surface needing backend work, S12 deletes what is now
dead. The app stays runnable and green throughout.

### S1 — Token layer + dual-theme palette + contrast test  *(small)*

Read: `frontend/src/styles.css` lines 1–130 only, `frontend/src/components/ThemeToggle.tsx`.

Add the Modernist tokens above for both themes **alongside** the existing glassmorphism tokens —
delete nothing yet. Add `frontend/src/test/contrast.test.ts` asserting all four bands clear 4.5:1
in **both** themes, plus the neutral pairs. That test is rule 8 made executable, and is what stops
a later session quietly breaking the palette.

Exit: new tokens present, contrast test passing, app visually unchanged, `tsc` + vitest green.

### S2 — App shell  *(medium)*

Read: `frontend/src/App.tsx`, `frontend/src/components/ApiKeyGate.tsx`.

244px sticky sidebar (brand, 8-item nav with the 3px active marker, footer block with pipeline
button, status/quota meter, theme toggle). Real routes: `/`, `/cohort`, `/person/:id`,
`/diagnostic`, `/ingest`, `/simulator`, `/history`, `/audit`. The three global banners in order:
run progress, use-constraint, degraded-tier. Sections render existing page bodies as placeholders.

**Drop the demo-state toggle** — it is a prototype affordance; empty and degraded come from the API.

Exit: all 8 routes reachable, both themes correct, keyboard nav and axe clean.

### S3 — Overview  *(small–medium)*

Read: `frontend/src/pages/Home.tsx`, `frontend/src/api/client.ts`.
Endpoints: `/api/v1/employees`, `/api/v1/calibration`.

Stat strip (4 cells), "It does / It does not" two-column block, three link cards, empty state.
Establishes the stat-strip pattern reused in S6 and S7.

**All four numerals `var(--ink)`** — a headcount of people is never in an alert colour.

Exit: populated and empty states both correct in both themes.

### S4 — Cohort  *(medium)*

Read: `frontend/src/pages/Console.tsx` (cohort part only), `frontend/src/components/RiskPill.tsx`,
`frontend/src/components/ConfidenceBadge.tsx`. Endpoint: `/api/v1/employees`.

Alphabetical two-column grid, 1px gap over `--rule` so the gap draws the lines. Deviation bars on
the `126px 1fr 1fr 62px` grid with the centre axis.

**No sort control — ever.** The repo's own copy promises the system never ranks people.

Exit: deviation bars correct for adverse/non-adverse in both themes; after-hours always inert.

### S5 — Person detail  *(large — split if budget is tight)*

Read: `frontend/src/pages/Console.tsx` (briefing part).
Endpoints: `/api/v1/employee/{name}/briefing`, `POST /api/v1/interventions`.

**5a:** the `300px 1fr` split, score column with confidence suppression (low/none → no number,
plausible range + caveat), attribution list, four-week trajectory.
**5b:** confirmed patterns (severity chips, *not* band colours), suggested next steps with
accept/dismiss POSTing for real, access-trail footer note.

Exit: a low-confidence subject renders **no** single number anywhere.

### S6 — Diagnostic room  *(medium)*

Read: `frontend/src/pages/DiagnosticRoom.tsx`. Endpoints: `/api/v1/calibration`,
`/api/v1/interventions/outcomes`, `POST /api/v1/feedback`.

Calibration stat strip, outcomes table honouring the reporting floor, verdict form on the
`220px 120px 1fr` grid.

**No free-text field** — the closed list is enforced at `src/api/routers/evolution.py:176`, and
adding one would let managers record exactly the data the allowlist exists to exclude.

Exit: a below-floor sample renders "withheld", never a number.

### S7 — Ingest  *(medium)*

Read: `frontend/src/pages/Console.tsx` (ingest part), `src/governance/allowlist.py` signatures only.
Endpoint: `POST /api/v1/ingest/raw`.

`1fr 340px` layout, CSV textarea, ingest receipt with the dropped-column box, allowlist panel right.
The allowlist panel needs a read endpoint (`permitted_fields()` / `_forbidden_categories()`) — add
it here, or fold into S10.

Exit: pasting a CSV containing `sentiment_score` shows it explicitly refused.

### S8 — Simulator  *(small–medium)*

Endpoint: `POST /api/v1/score/custom`.

`330px 1fr`, five sliders, recompute on change with no submit, 60px numeral with the chip beside
it, briefing draft panel.

Exit: every slider recomputes live; no value persists server-side.

### S9 — History  *(small–medium)*

Read: `frontend/src/pages/History.tsx`. Endpoints: `/api/v1/history`, `POST /api/v1/history/clear`.

Trajectory rows on `170px 1fr 210px`, operational event log, clear-with-inline-confirm.

The intro **must** keep the distinction: this is housekeeping, *not* the access trail. Clearing
touches only `src/app_utils/audit_log.py`, never `src/governance/audit.py`.

Exit: copy states the distinction; clear affects only the operational log.

### S10 — Backend: expose governance  *(medium, backend only)*

Read: `src/governance/audit.py`, `src/governance/retention.py`, `src/api/routers/system.py`.

The logic exists; the HTTP surface does not. Add read-only endpoints for `query_access()`,
`verify_chain()`, the retention policy, and the allowlist. Regenerate `openapi.json` and
`schema.ts` (CI diffs it).

**Read-only by construction** — no route may edit or delete an access-trail row.

Exit: endpoints and tests green, generated client not stale.

### S11 — Access trail and retention UI  *(medium)*

Table of When / Viewer / Subject / Purpose / Chain in monospace. Refusals render as ordinary rows
reading "REFUSED · purpose not on allowlist" — **a refusal is itself an audit record.** Retention
grid generated from config per decision 2.

**No control on this page may edit or delete a row.**

Exit: chain verification surfaced; zero mutating affordances in the DOM.

### S12 — Cleanup  *(small)*

Delete the glassmorphism tokens and dead rules from `styles.css`, remove the retired page
components, update `README.md` claims to match observable behaviour, add any simulated element to
`docs/LIMITATIONS.md`.

Exit: no dead CSS, no unreferenced components, full suite green.

---

## Rules that must survive every session

From the handoff's own list, all of which encode `CONTEXT.md` rather than taste:

1. No headcount of people ever rendered in an alert colour.
2. Band colours for classification only — never buttons, links, nav, or brand.
3. Never a bare score without confidence; low confidence suppresses the number entirely.
4. No sort-by-score control on the cohort view.
5. No free-text field on the feedback form.
6. Samples below the reporting floor are withheld, never reported.
7. The access trail has no edit or delete affordance anywhere.
8. Every band clears 4.5:1 against its paired background — **in both themes** (S1's test).

---

## Open question — needs a decision before S11

`src/governance/audit.py:227` documents that `subject_id` "must be the pseudonymous surrogate ID,
never a real name". The mockup's access trail has a **Subject** column, but `CLAUDE.md` rule 1 says
"first names only in output, never surnames or employee IDs".

A surrogate ID is not an employee ID, so this is arguably compliant — but it is the one place in
the redesign where a stable per-person identifier is rendered on screen, which is exactly what
rule 1 guards against. Options: show the surrogate, show the first name, or show neither and make
the column "Subject on record: yes / no". **Decide before building S11.**

---

## Revisions from review — 2026-08-22

Four changes to the handoff, from reviewing the running prototype. All override the mockup.

### R1 — Sidebar: drop the quota meter, show the active model instead  *(affects S2)*

The mockup's provider-call meter ("128 / 500", "Quota resets Monday 00:00 UTC") is **cut entirely**,
along with the handoff's instruction to wire it to a provider-usage endpoint. The system runs on
multiple free models with local fallback, and there is no intent to impose a hard limit in the UI
or in code — so a quota bar would be inventing a constraint that does not exist.

Replaced by a **model status block**: the model currently serving requests, and when one is
exhausted, the model it fell back to. Endpoint: `/api/v1/models/status`, `/api/v1/models`.
Keep the existing operational/degraded status square above it.

### R2 — Overview: dead space on the right  *(affects S3)*

The hero's `max-width: 16ch` plus the 1160px content cap leaves the right-hand side of the
Overview empty on a wide viewport. Wanted: a smoother, more considered use of that space.
Decide whether to widen the content, restructure the hero, or bring content up beside it —
without adding anything that ranks or lists people.

### R3 — Person detail: the four-week trajectory is too sparse  *(affects S5a)*

Four 56px bars under-fill the evidence column. Either resize the bars to fill the space, or
extend the window beyond four weeks. **Check what depth the backend actually holds before
choosing** — extending is only real if the data exists; otherwise it is a resize.

### R4 — Ingest: the other ingestion paths are missing  *(affects S7)*

The mockup shows CSV paste only. The backend has six paths — `ingest/raw`, `ingest/upload`,
`ingest/db`, `ingest/s3`, `ingest/webhook`, `ingest/natural-language`, plus the `db`/`s3` status
endpoints. The Ingest section must surface them rather than pretending paste is the only route.

### Decisions on the above — 2026-08-22

1. **R1** — show the **current model**, with a dropdown (or equivalent) revealing the full chain.
2. **R2** — **both B and C**: a band-distribution block (counts per band, never names) *and* a
   latest-run panel (last run time, number evaluated, data gaps). Together these fill the
   right-hand space beside the hero. The run panel's model line must not duplicate the sidebar's
   model block — reference it, don't repeat it.
3. **R3** — either resize or extend, implementer's call once backend depth is known.
4. **R4** — **list every ingestion method** as a dropdown or mini sidebar, with a **separate page
   per method**, because the inputs genuinely differ (a DB needs host, port, database, credentials;
   a bucket needs a region and a key). See R5 — this grew into its own track.

### R5 — Ingestion connectors are a backend track, not part of S7  *(new)*

Only **Excel upload and prompt extraction** are practically tested. The user wants genuinely
working backends for S3, Azure, PostgreSQL and MySQL. `docs/LIMITATIONS.md:13-24` already records
the true state, and it is further from "working" than the endpoint list suggests:

| Path | Actual state today |
| --- | --- |
| `ingest/upload` (Excel/CSV) | Real, tested |
| `ingest/natural-language` | Real, tested |
| `ingest/raw` | Real |
| `ingest/webhook` | Real, HMAC-authenticated |
| `ingest/s3` | Real `GetObject` **only if** AWS creds are configured; otherwise reads a local folder |
| `ingest/db` | **SQLite only**, and `seed_sample_corporate_batch()` fabricates the rows |
| Azure Blob | **Does not exist** |
| PostgreSQL / MySQL | **Do not exist** — `sql_store.py` is SQLite |

So this is new connector work, not UI work: real drivers, connection testing, and credential
handling. It must not ride inside S7, and until a connector is genuinely working its page carries
a `_simulated` label and a `docs/LIMITATIONS.md` line, per `CLAUDE.md`.

**S7 is therefore reduced to**: the ingestion shell — mini sidebar, one sub-page per method,
the allowlist panel, and the ingest receipt — wired to the paths that genuinely work today, with
the untested ones honestly labelled. Connectors become S13+.

### R6 — Connector credentials: entered manually, encrypted server-side  *(decided)*

Credentials are entered manually against the server, then a **Test connection** action reports
whether the fetch actually works. They are held server-side only — never in `localStorage`, never
in a cookie, never returned to the browser, so they cannot be read or altered from the devtools
console.

**Encrypted, not hashed — this distinction is load-bearing.** Hashing is one-way. It is correct for
the API keys in `src/config.py`, because those are only ever *verified* (`key_sha256`). A Postgres
password or an AWS secret key must be *presented* to a remote service, so it has to be recoverable:
that means symmetric **encryption at rest**, with the encryption key supplied by environment
variable and never written into `data/`. A hashed DB password can never connect to anything.

Design constraints for S13+:

- Write-only over HTTP: an admin-role endpoint accepts a credential; **no endpoint ever returns it**.
- The UI only ever sees a source *name*, its type, and a connection-test verdict.
- Test-connection failures surface a redacted reason — `CLAUDE.md` rule 4 forbids raw provider
  errors reaching users, and a driver error string routinely contains the host and user.
- Never logged, never in the audit trail's `detail` field (`gitleaks` runs over full history).
- Rotation and revocation must be possible without a redeploy.

Likely new dependency: `cryptography` (Fernet / AES-GCM) — needs a justification line in the commit.

### R7 — Archivo must be self-hosted; the handoff's font import cannot ship  *(found in S1)*

The handoff specifies Archivo via `@import` from Google Fonts. That is blocked in production:
`src/security/middleware.py` sets `default-src 'self'` with `style-src 'self' 'unsafe-inline'` and
**no `font-src` directive**, so the stylesheet is refused and the woff2 files fall back to
`default-src 'self'` and are refused too. Loosening the CSP to admit Google is the wrong trade —
it also leaks every viewer's IP to a third party, from a tool that reads employee telemetry.

Fix: vendor Archivo 400/600/800 woff2 into `frontend/public/fonts/` and declare `@font-face` with
same-origin URLs. Until then `--font-heading` / `--font-body` fall back to the system UI stack, and
**no session may claim the typography matches the design.** Blocks the visual sign-off on S2/S3.

### Still open — blocking S13+, not S7

1. **Drivers.** One SQLAlchemy dependency covering Postgres/MySQL/SQLite, or individual drivers
   (`psycopg`, `PyMySQL`)? Justification required either way.
2. **Priority.** No Azure Logic Apps or AWS components are available to test against, so the cloud
   connectors cannot be verified end-to-end yet. **Postgres first** is the pragmatic order — it runs
   locally via the existing `docker-compose.yml`, so it can be genuinely tested rather than
   labelled `_simulated`. Confirm.
