// frontend/src/pages/Home.tsx
//
// The landing page, and the last of the four migrated (§9's order puts it last
// because it shows off the least).
//
// It carries something the old dashboard did not: a plain statement of what
// this system is, what it deliberately is not, and what it may not be used for.
// That is not decoration on a surveillance-adjacent tool. The person operating
// it should meet the constraints before they meet the controls, and "we never
// compare people to each other" is a claim they can hold the tool to.

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import type { CalibrationView, EmployeeSummary, ProviderStatus } from "../api/types";

export function Home() {
  return (
    <main className="page" aria-labelledby="home-heading">
      <h1 id="home-heading">Quiet-Quitting Detector</h1>
      <p className="page__intro">
        Weekly engagement telemetry, evaluated for each person against their own
        history, turned into a supportive prompt for a conversation.
      </p>

      <StancePanel />
      <StatusPanel />

      <nav aria-label="Sections" className="panel">
        <h2>Where to go</h2>
        <ul className="cards">
          <li>
            <Link to="/diagnostic">Diagnostic room</Link>
            <p>Is the system right? What happened after managers acted?</p>
          </li>
          <li>
            <Link to="/console">Console</Link>
            <p>The cohort, data ingest, and the what-if simulator.</p>
          </li>
          <li>
            <Link to="/history">History</Link>
            <p>Each person's own trajectory, and the operational event log.</p>
          </li>
        </ul>
      </nav>
    </main>
  );
}

function StancePanel() {
  return (
    <section aria-labelledby="stance-heading" className="panel panel--stance">
      <h2 id="stance-heading">What this is, and what it is not</h2>
      <div className="stance">
        <div>
          <h3>It does</h3>
          <ul>
            <li>Compare each person to their <strong>own</strong> earlier weeks.</li>
            <li>
              Require a pattern to hold for two or more consecutive weeks, and to
              still be happening now.
            </li>
            <li>Say when it is not confident, instead of showing a number.</li>
            <li>Explain which metric drove a score.</li>
          </ul>
        </div>
        <div>
          <h3>It does not</h3>
          <ul>
            <li>Rank people, or compare one person to another.</li>
            <li>Recommend disciplinary action, ever.</li>
            <li>
              Hold anything about health, sentiment, or performance ratings —
              there is no field for them.
            </li>
            <li>Treat missing data as evidence of anything.</li>
          </ul>
        </div>
      </div>
      <p className="callout callout--caveat">
        This is a prompt for a conversation, not a verdict about a person. If it
        is ever used to justify a decision about someone's employment, it is
        being used for something it was explicitly built not to do.
      </p>
    </section>
  );
}

function StatusPanel() {
  const employees = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<EmployeeSummary[]>("/employees"),
  });
  const calibration = useQuery({
    queryKey: ["calibration"],
    queryFn: () => api.get<CalibrationView>("/calibration"),
  });
  const providers = useQuery({
    queryKey: ["provider-status"],
    queryFn: () => api.get<ProviderStatus>("/models/status"),
  });

  const error = employees.error ?? calibration.error ?? providers.error;

  return (
    <section aria-labelledby="status-heading" className="panel">
      <h2 id="status-heading">Right now</h2>
      {error ? <ErrorNote error={error} /> : null}

      <dl className="stats">
        <div>
          <dt>People on record</dt>
          <dd>{employees.data?.length ?? "—"}</dd>
        </div>
        <div>
          {/* A count, never a list of who. The landing page is not the place to
              put names next to a risk word. */}
          <dt>Currently raised above Healthy</dt>
          <dd>
            {employees.data
              ? employees.data.filter((e) => e.classification !== "Healthy").length
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Manager verdicts recorded</dt>
          <dd>{calibration.data?.overall.total ?? "—"}</dd>
        </div>
        <div>
          <dt>Scoring</dt>
          <dd>{providers.data?.local_only_mode ? "Local only" : "Provider chain"}</dd>
        </div>
      </dl>

      {calibration.data && !calibration.data.overall.total ? (
        <p className="callout callout--caveat">
          No manager has told this system whether it was right yet, so nothing it
          reports has been validated. Treat every assessment as a question.
        </p>
      ) : null}

      {calibration.data?.review_required ? (
        <p role="alert" className="callout callout--alert">
          Calibration is outside the acceptable range.{" "}
          <Link to="/diagnostic">Review it before relying on any assessment.</Link>
        </p>
      ) : null}
    </section>
  );
}
