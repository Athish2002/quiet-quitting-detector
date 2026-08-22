// frontend/src/pages/Home.tsx
//
// Section 1: Overview (/)
//
// An ethical, per-person view of team wellbeing. The landing section establishes
// the tool's core premise before any detail is shown: telemetry is read against
// a person's own history, never against a cohort ranking.
//
// Replaces the old glassmorphism Home page in S3 of the Modernist redesign.

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import { SectionHeader } from "../components/SectionHeader";
import type { CalibrationView, EmployeeSummary } from "../api/types";

export function Home() {
  const employees = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<EmployeeSummary[]>("/employees"),
  });
  const calibration = useQuery({
    queryKey: ["calibration"],
    queryFn: () => api.get<CalibrationView>("/calibration"),
  });

  const error = employees.error ?? calibration.error;
  const data = employees.data ?? [];
  const cal = calibration.data?.overall;

  // Counts for the 4 bands (counts ONLY, never names, never sorted by score)
  const healthyCount = data.filter((e) => e.classification === "Healthy").length;
  const watchCount = data.filter((e) => e.classification === "Watch").length;
  const atRiskCount = data.filter((e) => e.classification === "At Risk").length;
  const exitCount = data.filter((e) => e.classification === "Silent Exit").length;
  const elevatedCount = watchCount + atRiskCount + exitCount;

  // Latest run statistics
  const latestWeek = data.length > 0 ? Math.max(...data.map((e) => e.latest_week)) : null;
  const evaluatedCount = data.length;
  const gapCount = data.filter(
    (e) => e.degraded || e.confidence === "low" || e.confidence === "none",
  ).length;

  const totalPeople = employees.data !== undefined ? data.length : null;
  const totalVerdicts = cal ? cal.total : null;
  const harmfulVerdicts = cal ? cal.harmful : null;

  return (
    <div className="overview-page">
      {error ? <ErrorNote error={error} /> : null}

      {/* 1. Hero & R2 (SectionHeader left, Band distribution + Latest run right) */}
      <div className="overview-hero">
        <SectionHeader
          eyebrow="OVERVIEW"
          title="Weekly telemetry, read against a person's own history."
          intro="An ethical, per-person view of team wellbeing. The system flags sustained divergence from an employee's own baseline and drafts supportive manager briefings — it never ranks people or compares one person to another."
          wide={true}
        />

        <aside className="overview-side" aria-label="Current status and evaluation summary">
          {/* R2 (a): Band distribution block */}
          <div className="overview-side__card" aria-labelledby="band-dist-heading">
            <p id="band-dist-heading" className="overview-side__title">
              Current distribution
            </p>
            <ul className="distribution-list" aria-label="People per classification band">
              <li className="distribution-item">
                <span className="chip chip--healthy">Healthy</span>
                <span className="distribution-count">{employees.isLoading ? "—" : healthyCount}</span>
              </li>
              <li className="distribution-item">
                <span className="chip chip--watch">Watch</span>
                <span className="distribution-count">{employees.isLoading ? "—" : watchCount}</span>
              </li>
              <li className="distribution-item">
                <span className="chip chip--at-risk">At Risk</span>
                <span className="distribution-count">{employees.isLoading ? "—" : atRiskCount}</span>
              </li>
              <li className="distribution-item">
                <span className="chip chip--exit">Silent Exit</span>
                <span className="distribution-count">{employees.isLoading ? "—" : exitCount}</span>
              </li>
            </ul>
          </div>

          {/* R2 (b): Latest run panel */}
          <div className="overview-side__card" aria-labelledby="latest-run-heading">
            <p id="latest-run-heading" className="overview-side__title">
              Latest evaluation
            </p>
            <div className="latest-run-metrics">
              <div className="latest-run-metric">
                <span>Evaluated</span>
                <strong>{employees.isLoading ? "—" : `${evaluatedCount} people`}</strong>
              </div>
              <div className="latest-run-metric">
                <span>Latest telemetry</span>
                <strong>
                  {employees.isLoading
                    ? "—"
                    : latestWeek !== null
                      ? `Week ${latestWeek}`
                      : "None"}
                </strong>
              </div>
              <div className="latest-run-metric">
                <span>Data gaps</span>
                <strong>{employees.isLoading ? "—" : `${gapCount} with gaps`}</strong>
              </div>
            </div>
            <p className="latest-run-note">Active model: see sidebar</p>
          </div>
        </aside>
      </div>

      {/* 3. Stat strip: 4 equal columns with rules between & under */}
      <section aria-label="Summary statistics" className="stat-strip">
        <div className="stat-cell">
          <p className="stat-cell__label">People on record</p>
          <p className="stat-cell__numeral">
            {employees.isLoading ? "—" : totalPeople ?? 0}
          </p>
          <p className="stat-cell__note">Active in current cohort</p>
        </div>
        <div className="stat-cell">
          <p className="stat-cell__label">Currently raised above Healthy</p>
          <p className="stat-cell__numeral">
            {employees.isLoading ? "—" : elevatedCount}
          </p>
          <p className="stat-cell__note">Watch, At Risk, or Silent Exit</p>
        </div>
        <div className="stat-cell">
          <p className="stat-cell__label">Manager verdicts recorded</p>
          <p className="stat-cell__numeral">
            {calibration.isLoading ? "—" : totalVerdicts ?? 0}
          </p>
          <p className="stat-cell__note">Feedback on model accuracy</p>
        </div>
        <div className="stat-cell">
          <p className="stat-cell__label">Reported as harmful</p>
          <p className="stat-cell__numeral">
            {calibration.isLoading ? "—" : harmfulVerdicts ?? 0}
          </p>
          <p className="stat-cell__note">Verdicts flagged harmful</p>
        </div>
      </section>

      {/* 6. Empty state notice / calibration caveat */}
      {calibration.data && !calibration.data.overall.total ? (
        <div className="overview-notice" role="status">
          <p>
            <strong>No manager verdicts recorded.</strong> No manager has told this system
            whether it was right yet, so nothing it reports has been validated. Treat every
            assessment as a question.
          </p>
        </div>
      ) : null}

      {calibration.data?.review_required ? (
        <div className="overview-notice overview-notice--alert" role="alert">
          <p>
            <strong>Calibration review required.</strong> Calibration is outside the acceptable
            range.{" "}
            <Link to="/diagnostic">Review it before relying on any assessment.</Link>
          </p>
        </div>
      ) : null}

      {/* 4. What this is, and what it is not */}
      <section aria-labelledby="stance-heading" className="stance-section">
        <h2 id="stance-heading" className="sr-only">
          Ethical Safeguards &amp; Governance
        </h2>
        <div className="stance-grid">
          <div className="stance-col">
            <p className="stance-col__label">It does</p>
            <ul className="stance-list">
              <li>
                Compare each person to their <strong>own</strong> earlier weeks.
              </li>
              <li>
                Require a pattern to hold for two or more consecutive weeks, and to still be
                happening now.
              </li>
              <li>Say when it is not confident, instead of showing a number.</li>
              <li>Explain which metric drove a score.</li>
            </ul>
          </div>
          <div className="stance-col">
            <p className="stance-col__label">It does not</p>
            <ul className="stance-list">
              <li>Rank people, or compare one person to another.</li>
              <li>Recommend disciplinary action, ever.</li>
              <li>
                Hold anything about health, sentiment, or performance ratings — there is no
                field for them.
              </li>
              <li>Treat missing data as evidence of anything.</li>
            </ul>
          </div>
        </div>
        <p className="stance-closing">
          This is a prompt for a conversation, not a verdict about a person. If it is ever used to
          justify a decision about someone's employment, it is being used for something it was
          explicitly built not to do.
        </p>
      </section>

      {/* 5. Three Link Cards */}
      <section aria-labelledby="links-heading" className="overview-links">
        <h2 id="links-heading" className="sr-only">
          Core sections
        </h2>
        <div className="link-cards-grid">
          <Link to="/cohort" className="link-card">
            <p className="link-card__eyebrow">Section 02</p>
            <h3 className="link-card__title">Cohort</h3>
            <p className="link-card__body">
              Weekly telemetry across the full cohort. Alphabetical, unranked, with deviation bars
              against each person's own baseline.
            </p>
            <span className="link-card__action">Open cohort &rarr;</span>
          </Link>

          <Link to="/diagnostic" className="link-card">
            <p className="link-card__eyebrow">Section 04</p>
            <h3 className="link-card__title">Diagnostic room</h3>
            <p className="link-card__body">
              Model calibration, harm rates, and the closed-vocabulary manager verdict form.
            </p>
            <span className="link-card__action">Open diagnostic room &rarr;</span>
          </Link>

          <Link to="/audit" className="link-card">
            <p className="link-card__eyebrow">Section 08</p>
            <h3 className="link-card__title">Access trail</h3>
            <p className="link-card__body">
              Immutable cryptographic log of every assessment opened, who viewed it, and retention
              schedules.
            </p>
            <span className="link-card__action">Open access trail &rarr;</span>
          </Link>
        </div>
      </section>
    </div>
  );
}
