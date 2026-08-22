# Handoff: Quiet-Quitting Detector — full UI redesign

Target repo: `Athish2002/quiet-quitting-detector` (branch `main`)
Target surface: `frontend/` — React + TypeScript + Vite, existing pages `Home.tsx`, `Console.tsx`, `DiagnosticRoom.tsx`, `History.tsx`.

## Overview

A complete visual and structural redesign of the frontend. The current app is four
sibling pages; the redesign is a **single app shell with a fixed left sidebar** and eight
sections. It keeps every behaviour the backend already supports (ingest, run, feedback,
simulate, history) and adds surfaces for governance features that exist in the Python
domain layer but were never exposed in the UI (allowlist enforcement, access audit trail,
retention policy, confidence suppression, degraded tier).

## About the design files

`Quiet Quitting Detector.dc.html` is a **design reference created in HTML**, not production
code. It is a self-contained prototype with mock data so every screen and interaction can be
clicked through. Do **not** copy it into the repo. The task is to recreate it inside the
existing `frontend/` React + TypeScript app, wired to the real FastAPI endpoints, using the
project's existing patterns.

`support.js` is the prototype's runtime shim only — it has no equivalent in the target app
and must not be ported. `_ds/.../styles.css` is the design system the prototype loads; port
its **token values** (below), not the file.

Open the HTML file directly in a browser to click through every screen.

## Fidelity

**High-fidelity.** Final colours, typography, spacing and interaction states. Recreate
pixel-accurately, but express it in the codebase's own idioms (CSS modules / Tailwind /
styled-components — whatever `frontend/` already uses). All values below are exact.

---

## Design tokens

Declare once as CSS custom properties on `:root`.

### Colour

| Token | Value | Role |
| --- | --- | --- |
| `--paper` | `#F2F5F4` | Page background, sidebar background |
| `--surface` | `#FFFFFF` | Cards, panels, the use-constraint banner, light text on dark fills |
| `--ink` | `#1B2422` | Body text, all stat numerals, active nav background |
| `--muted` | `#5A6A66` | Secondary/meta text, labels, captions |
| `--rule` | `#D2DAD7` | Dividers, borders, progress-bar tracks, inert bars |
| `--accent` | `#1D4E6B` | Brand mark, section eyebrows, primary button, focus ring, active-nav marker |
| `--accent-bg` | `#EAF1F5` | Accent tint — nav hover, card hover, selected demo-state, selected verdict |

### Classification bands

Reserved **exclusively** for classification labels. Never on buttons, links, nav, brand, or
any count of people. Foreground on its paired background; both verified ≥ 4.5:1.

| Band | Foreground | Background | Contrast |
| --- | --- | --- | --- |
| Healthy | `#47795A` | `#EDF4EF` | 4.59:1 |
| Watch | `#8A6A22` | `#FAF4E6` | 4.59:1 |
| At Risk | `#9E5333` | `#FAEFEA` | 4.96:1 |
| Silent Exit | `#7E3A2C` | `#F9EDEA` | 7.29:1 |

Two of these were darkened from the original brief to clear 4.5:1 — Watch from `#A8802F`
(3.31:1) and At Risk from `#A85A38` (4.45:1). Do not revert them.

A classification is always rendered as **tinted background + band-colour text + 1px
band-colour border + the classification spelled out in words**. Never a bare colour dot.

### Typography

Archivo throughout (`@import` from Google Fonts, weights 400/600/800).
`--font-heading` and `--font-body` are both Archivo; headings are weight 800,
`line-height: 1.12`, `letter-spacing: -0.015em`.

| Use | Size | Weight |
| --- | --- | --- |
| Overview h1 | 44px | 800 |
| Section h1 | 38px | 800 |
| h2 | 26px | 800 |
| h3 | 20px | 800 |
| Card / person name | 17–19px | 800 |
| Body | 15px | 400 |
| Dense body / table | 13–14px | 400 |
| Meta, captions | 11–12.5px | 400 |
| Eyebrow / uppercase label | 10–11px, `letter-spacing: 0.09–0.1em`, `text-transform: uppercase` | 400 |
| Risk numeral (person) | 66px | 800 |
| Risk numeral (simulator) | 60px | 800 |
| Stat numerals | 40px (overview), 34px (diagnostic), 26px (ingest) | 800 |

`font-variant-numeric: tabular-nums` is set on the app shell and inherits everywhere, so
figures don't shift width between states. Keep it.

### Geometry

- **Border radius: 0 everywhere.** No exceptions.
- Spacing scale: 4 / 8 / 12 / 16 / 24 / 32px.
- Major section rules: `2px solid var(--rule)`. Row rules: `1px solid var(--rule)`.
- No shadows anywhere in this design. Elevation is expressed by rules and fills.
- Content max-width 1160px; sidebar 244px fixed.

### Interaction states

- Hover on nav items and cards: background `var(--accent-bg)`.
- Primary button: `var(--accent)` fill, `var(--surface)` text; hover `#173E55`; active `#12303F`.
- Secondary button: transparent with `1px solid var(--rule)`; hover a 7% ink tint.
- Focus: `outline: 3px solid var(--accent); outline-offset: 2px` — never the browser default.
- Disabled: `opacity: 0.45`.

---

## App shell

**Sidebar** — 244px, fixed, `position: sticky; top: 0; height: 100vh`, `2px solid var(--rule)`
right border, `var(--paper)` background, 24px/16px padding.

Top to bottom:
1. **Brand** — a 14×14px `var(--accent)` square, then "Quiet-Quitting / Detector" in Archivo 800/16px on two lines. Under it, the uppercase strapline "Wellbeing prompt · not a verdict" in `var(--muted)` at 10.5px.
2. **Nav** — 8 items, 13.5px, 7px/10px padding, 2px gap. Active item: `var(--ink)` background, `var(--surface)` text, weight 600, and a 3px full-height `var(--accent)` marker on the left edge. Inactive: transparent, hover `var(--accent-bg)`.
3. **Footer block** (pushed down with `margin-top: auto`, `2px solid var(--rule)` top border):
   - Uppercase label "Pipeline", then a full-width primary button — label "Run the pipeline", or "Run in progress…" and disabled while a run is active.
   - Uppercase label "Demo state", then three small toggle buttons: Populated / First run (empty) / Degraded tier. Selected gets `var(--accent-bg)` background and `var(--accent)` text. **This is a prototype affordance for demoing the empty and fallback states — drop it in production and drive those states from real API responses.**
   - **Status & quota block** (`1px solid var(--rule)` top border): an 8×8px status square — `var(--healthy)` when operational, `var(--watch)` when degraded — beside a bold 11.5px label ("All services operational" / "Degraded · local fallback"). Below it a provider-call meter: the caption "Provider calls" in `var(--muted)` on the left and `128 / 500` in `var(--ink)` weight 600 on the right, a 6px track (`var(--rule)`) with an `var(--accent)` fill at the used percentage, and a 10.5px `var(--muted)` note ("Quota resets Monday 00:00 UTC", or "Provider chain unreachable · 0 calls billed" when degraded). **Wire this to the real provider-usage endpoint.**
   - A 10.5px `var(--muted)` line: "Local scoring · model qq-local-2.3".

**Main** — `flex: 1`, padding `30px 40px 72px`, max-width 1160px.

### Global banners (render above the active section, in this order)

1. **Run progress** — only while running. `2px solid var(--accent)` box: "Evaluating {name}" in Archivo 800/13px, a flexible 8px track with an `var(--accent)` fill, and "{n} of {total}" at 12px.
2. **Use-constraint banner** — `var(--surface)` background with a **4px `var(--ink)` left rule** (not a filled block: it is a standing condition, not an error). A 132px-wide uppercase `var(--accent)` label "Use constraint", then 13.5px body copy: *"This system compares each person only to their own earlier weeks. It does not rank people, does not recommend disciplinary action, and must never be used to justify a decision about someone's employment. Every assessment you open is written to the access trail."*
3. **Degraded-tier notice** — only in degraded mode. `2px solid var(--accent)` box: *"**Degraded tier.** The provider chain is unavailable, so scores come from the local fallback scorer. Confidence is capped at "Not sure yet" and no single number is shown for anyone."*

---

## Sections

Every section opens with an uppercase 11px `var(--accent)` eyebrow, then an h1, then a 15px
`var(--muted)` intro paragraph (max-width 70ch), then a 2px rule.

### 1. Overview (`/`)

- h1 (44px, max-width 16ch): "Weekly telemetry, read against a person's own history."
- Intro at 16px, max-width 60ch.
- **Stat strip** — 4 equal columns, `1px solid var(--rule)` between, `2px solid var(--rule)` under. Each cell: uppercase label (10.5px `var(--muted)`, `min-height: 28px` so numerals align), a 40px Archivo-800 numeral, and an 11.5px `var(--muted)` note.
  Cells: People on record / Currently raised above Healthy / Manager verdicts recorded / Reported as harmful.
  **All four numerals are `var(--ink)`, with no exceptions — a headcount of people is never rendered in an alert colour.**
- **"What this is, and what it is not"** — two columns split by a 1px rule, each headed by an uppercase `var(--accent)` label ("It does" / "It does not") over a 14px bulleted list. Below the pair, a 2px rule and a closing 14px `var(--muted)` paragraph.
- **Three link cards** — `var(--surface)` on `1px solid var(--rule)`, hover borders `var(--accent)` and fills `var(--accent-bg)`. Titles: Cohort, Diagnostic room, Access trail.
- Empty state: when nothing is ingested, numerals read `0` / `—` and an extra `2px solid var(--accent)` notice appears: *"No manager has told this system whether it was right yet…"*

### 2. Cohort

Alphabetical two-column grid, `1px` gap over a `var(--rule)` background so the gap draws the
grid lines. Cells are `var(--paper)`, 18px/20px padding, hover `var(--surface)`, whole cell
clickable → person detail.

**There is deliberately no sort control.** The repo's own copy promises the system never
ranks people; a sort-by-score control would make this a leaderboard. Do not add one.

Each cell:
- Name (Archivo 800/19px) and team/tenure meta (11px `var(--muted)`) on the left; classification chip and confidence label right-aligned.
- **Deviation bars** — one row per metric on a `126px 1fr 1fr 62px` grid: metric label, a left half that fills right-to-left against a `2px var(--muted)` centre axis, a right half that fills left-to-right, and the signed percentage right-aligned. Bars are 9px tall. Width = `min(|delta|, 100)%`. Adverse movement is `var(--accent)` with `var(--ink)` text; non-adverse is `var(--rule)` with `var(--muted)` text. "Adverse" means below own baseline for tasks/hours, above for response time; after-hours logins carry no risk weight and are always inert.
- A 12px `var(--muted)` headline: "*N* confirmed patterns · *first pattern*" or "No confirmed patterns in this window."
- Empty state: a bordered panel, "Nobody on record yet", and a primary button to Ingest.

### 3. Person detail

- A ghost "← Back to cohort" button, then h1 name + classification chip + "team · latest week N".
- **Two columns, `300px 1fr`**, split by a 1px rule, closed by a 2px rule.
  - **Left — the score.** When confidence is `low` or `none` the number is **suppressed**: instead show a 19px Archivo-800 line "We are not confident enough to give a single number here.", then "Plausible range **3–7** out of 10", a confidence chip, and an 11.5px caveat that the range is a rule of thumb and not a statistical confidence interval. When confidence is sufficient: uppercase "Risk index", a 66px `var(--ink)` numeral with a "/ 10" suffix at 18px `var(--muted)`, the plausible range at 13px, and a confidence chip. Under either, the rationale at 13px.
  - **Right — the evidence.** "What drove it": per attribution, metric name + direction + week span on the left, "N% of the index" right-aligned, and a 10px `var(--rule)` track with an `var(--accent)` fill. Then "Four-week trajectory": four 56px bars, height `score × 8.4px`, coloured by that week's band foreground, with the score above and `W{n}` + band name below. Weeks with no data render a 4px `var(--rule)` stub and "—".
- **Two columns below**, split by a 1px rule:
  - **Confirmed patterns** — name (Archivo 800/14px), a severity chip, week span right-aligned, and detail copy. Severity chips are **not** band colours: low = `var(--paper)` on `var(--muted)` text, medium = `var(--rule)` on `var(--ink)`, high = `var(--ink)` on `var(--surface)`.
  - **Suggested next steps** — cards on `var(--surface)` with a 1px rule: title, rationale, then **Accept** (primary) and **Not this** (secondary). Accepting replaces the buttons with an `var(--accent)` chip "Recorded · outcome tracked from week 5". Dismissing removes the buttons.
- Footer note (11.5px `var(--muted)`): the view has been written to the hash-chained access trail and cannot be deleted from this interface, with a link to the access trail.

### 4. Diagnostic room

- Intro varies: unvalidated when no verdicts exist, otherwise the sample-size caveat.
- If the system is outside its operating range, an `var(--accent)` filled block: *"This system is outside its acceptable operating range. Consider rolling back the active model…"*
- **Four calibration stats** in the same strip pattern, rules top and bottom. Verdicts recorded / Confirmed when raised above Healthy / Reported as harmful / Active model. **All numerals `var(--ink)`, including "Reported as harmful".**
- **"What happened after managers acted"** — a caption in `var(--accent)` noting association not cause, then a table: Kind of action / Measured / Improved / Declined / No detectable change. Rows below the reporting floor show "*n* — below the reporting floor, withheld" in 12.5px `var(--muted)` with em-dashes in the numeric columns. **Never report a sample below the floor.**
- **Verdict form** — a `220px 120px 1fr` grid: a person select, a week number input, and three stacked verdict buttons (Accurate / Not accurate / Harmful), each with a 12px square marker that fills `var(--accent)` when selected and an `var(--accent-bg)` background. A primary "Record verdict" button, and on success a 13px `var(--accent)` confirmation. **There is deliberately no free-text field** — the copy says so, and adding one would let managers record health and circumstance data the allowlist exists to keep out.

### 5. Ingest

`1fr 340px` two-column layout.

- Left: a 140px "Default week" number input with an inline note, a 9-row monospace CSV textarea, then **Ingest** (primary, disabled while empty) and **Paste sample week** (secondary).
- **Ingest receipt** appears after submit: a three-cell stat strip (Rows accepted / Columns kept / Columns dropped, all numerals `var(--ink)`); then, if anything was dropped, a `2px solid var(--accent)` box headed "Dropped by the allowlist" naming each dropped column; then "Ingested. Run the pipeline to evaluate the new data."
- Right: an **Allowlist** panel on `var(--surface)`. Each row is a 7px status square, the field name in monospace 11.5px, and its status right-aligned. Permitted/identifier fields get a `var(--muted)` square; refused fields (`sentiment_score`, `performance_rating`, `health_*`) get `var(--ink)`.

### 6. Simulator

`330px 1fr`, split by a 1px left rule with 32px padding.

- Left: a name text input, then five range sliders (Week, Tasks completed, Response time, After-hours logins, Weekly hours), each showing "baseline *n*" in `var(--muted)` on the left and the live value in weight 600 on the right. `accent-color: var(--accent)`.
- Right: uppercase "Live result", then a **60px `var(--ink)` numeral with the classification chip vertically centred beside it at a 22px gap** (outlined, so the band colour reads as a label rather than a fill), the rationale at 14px, the confirmed-signal list with severity chips and `+weight` right-aligned, and a "Manager briefing draft" panel on `var(--surface)` headed by an uppercase `var(--accent)` label.
- Recomputes on every slider change with no submit.

### 7. History

- Per-person rows on a `170px 1fr 210px` grid, 1px rules between: name + meta, four 46px trajectory bars (height `score × 4.6px`, coloured by that week's band foreground, score above and `W{n}` below), then the classification chip and an "Open" secondary button.
- **"Operational event log"** — a table of When / Event / Detail. The intro must keep its distinction: this is housekeeping, **not** the access audit trail. Failed events render their type in `var(--accent)`.
- "Clear event log" (secondary) expands into an inline confirm: "Clear the operational log?" + "Yes, clear it" (primary) + "Cancel" (secondary). **This clears only the operational log — the access trail has no delete control anywhere in the UI, by design.**

### 8. Access trail & retention

- A table of When / Viewer / Subject / Purpose / Chain, monospace for timestamps and hashes. Refused requests appear as ordinary rows with the purpose reading "REFUSED · purpose not on allowlist" — **a refusal is itself an audit record.**
- **Retention grid** — 3 columns, `1px` gap over `var(--rule)`, cells on `var(--paper)`: kind, period (24px Archivo 800), and a 12px note. Raw weekly rows 90 days / Derived assessments 180 days / Manager verdicts 2 years / Access trail 7 years / Simulator scratch session / Refused requests 2 years.
- Closing note: purpose limitation is enforced server-side and refusals are logged.
- **This page must contain no control that edits or deletes a row.**

---

## Interactions & behaviour

- Nav switches sections; no route change is modelled in the prototype, but the target app should use real routes (`/`, `/cohort`, `/person/:id`, `/diagnostic`, `/ingest`, `/simulator`, `/history`, `/audit`).
- "Run the pipeline" steps through subjects at ~340ms each, updating the progress banner, then prepends a `run.complete` row to the event log. **Replace this with real progress from the backend** — poll or stream; do not fake the timing.
- Clicking a cohort cell or a history "Open" button navigates to that person.
- Accept/dismiss on an intervention is local in the prototype; POST it in the target app.
- Recording a verdict increments the verdict count and, when the verdict is "harmful", the harm count. Both must persist server-side.
- Ingest parses the pasted CSV header, drops disallowed columns, and writes a receipt plus an event-log row.
- Demo-state switching swaps the whole dataset. In production, "empty" is the no-data response and "degraded" is the fallback-scorer response — both come from the API, not a toggle.

## State

`view`, `personId`, `mode` (populated/empty/degraded), `running`/`runDone`/`runCurrent`,
`fbName`/`fbWeek`/`fbVerdict`/`fbDone`, `ingestWeek`/`ingestCsv`/`ingestResult`,
`sim` (name, week, tasks, response, after, hours), `accepted`/`dismissed` maps, `events`,
`confirmingClear`. In the target app most of these become server state — use whatever
fetching layer `frontend/` already has rather than local state.

## Rules to preserve

These are not styling preferences; they encode the product's stated position and several are
enforced in the Python domain layer.

1. No headcount of people is ever rendered in an alert colour.
2. The four band colours are used for classification only — never on buttons, links, nav, or brand.
3. Never a bare score without its confidence; low confidence suppresses the number entirely and shows a range.
4. No sort-by-score control on the cohort view.
5. No free-text field on the feedback form.
6. Samples below the reporting floor are withheld, never reported.
7. The access trail has no edit or delete affordance.
8. Every band colour clears 4.5:1 against its paired background — re-check if you retune any of them.

## Assets

None. No images, no icon font, no SVG illustration. If icons are added later the design
system specifies Lucide.

## Files in this bundle

- `Quiet Quitting Detector.dc.html` — the design reference. Open in a browser; click through all eight sections and all three demo states.
- `_ds/modernist-.../styles.css` — the Modernist design system the prototype loads. Port the token values, not the file.
- `support.js` — prototype runtime shim. Ignore; it has no target-app equivalent.
