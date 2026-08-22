import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import type { CalibrationView, EmployeeSummary, ProviderStatus } from "../api/types";

export function Home() {
  return (
    <main className="page home-page" aria-labelledby="home-heading">
      {/* Hero Section */}
      <section className="hero-section">
        <div className="hero-eyebrow">
          <span className="hero-eyebrow__dot"></span>
          Enterprise Multi-Agent Intelligence
        </div>
        <h1 id="home-heading" className="hero-title">
          Quiet-Quitting <span className="hero-title__gradient">Detector</span>
        </h1>
        <p className="hero-description">
          Ethical, per-employee engagement telemetry. Evaluated for each person against
          their own baseline, turning disengagement signals into supportive conversation blueprints.
        </p>
        <div className="hero-actions">
          <Link to="/cohort" className="btn btn--primary">
            Launch Cohort Console
          </Link>
          <Link to="/diagnostic" className="btn btn--glass">
            Open Diagnostic Room
          </Link>
        </div>
      </section>

      {/* The constraints come before the controls, and that ordering is the
          point: "we never compare people to each other" is a claim the operator
          should be able to hold this tool to before they start using it. Four
          tests and an E2E spec assert the wording below. */}
      <StancePanel />

      {/* Live System Telemetry Panel */}
      <StatusPanel />

      {/* Navigation Feature Grid */}
      <section className="panel section-features" aria-labelledby="features-heading">
        <h2 id="features-heading">Core Capabilities</h2>
        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-card__icon">📊</div>
            <h3>
              <Link to="/cohort">Cohort Console</Link>
            </h3>
            <p>
              Monitor team-wide disengagement signals, manage multi-source telemetry ingestion,
              and execute what-if intervention simulations.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-card__icon">🔍</div>
            <h3>
              <Link to="/diagnostic">Diagnostic Room</Link>
            </h3>
            <p>
              Deep-dive into individual employee trajectories, review risk driver explanations,
              and generate empathetic manager briefing scripts.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-card__icon">📈</div>
            <h3>
              <Link to="/history">Trajectory & History</Link>
            </h3>
            <p>
              Track historical weekly progress over time, review audit log trails, and measure
              the real-world impact of post-intervention actions.
            </p>
          </div>
        </div>
      </section>

      {/* Multi-Agent Architecture Overview */}
      <section className="panel section-architecture" aria-labelledby="arch-heading">
        <h2 id="arch-heading">4-Agent Autonomous Pipeline</h2>
        <p className="hint">
          Every evaluation passes through an isolated 4-agent network designed to eliminate bias and prevent punitive scoring.
        </p>
        {/* h3, not h4: the section heading is an h2 and skipping a level is a
            real axe violation, not a style preference. */}
        <div className="agent-pipeline">
          <div className="agent-step">
            <span className="agent-step__num">01</span>
            <h3>Orchestrator Agent</h3>
            <p>Validates telemetry schemas and sequences chronological baseline evaluation.</p>
          </div>
          <div className="agent-step">
            <span className="agent-step__num">02</span>
            <h3>Trend Detector</h3>
            <p>Identifies multi-week disengagement signals against an employee's personal history.</p>
          </div>
          <div className="agent-step">
            <span className="agent-step__num">03</span>
            <h3>Risk Scorer</h3>
            <p>Computes risk indices while enforcing confidence suppression thresholds.</p>
          </div>
          <div className="agent-step">
            <span className="agent-step__num">04</span>
            <h3>Manager Briefing</h3>
            <p>Synthesizes supportive, non-punitive dialogue templates and action plans.</p>
          </div>
        </div>
      </section>
    </main>
  );
}

function StancePanel() {
  return (
    <section aria-labelledby="stance-heading" className="panel panel--stance">
      <h2 id="stance-heading">Ethical Safeguards & Governance</h2>
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
    <section aria-labelledby="status-heading" className="panel section-status">
      <div className="section-status__header">
        <h2 id="status-heading">Live System Telemetry</h2>
        <span className="status-live-badge">
          <span className="status-live-badge__dot"></span> Live API Active
        </span>
      </div>
      
      {error ? <ErrorNote error={error} /> : null}

      <dl className="stats stats--cards">
        <div className="stat-card">
          <dt>People on record</dt>
          <dd>{employees.data?.length ?? "—"}</dd>
        </div>
        <div className="stat-card">
          {/* A count, never a list of who, and labelled as what it actually is.
              "Disengagement Signals" reads as a count of signals; this is a
              count of PEOPLE, and the landing page is not the place to put
              names next to a risk word. */}
          <dt>Currently raised above Healthy</dt>
          <dd>
            {employees.data
              ? employees.data.filter((e) => e.classification !== "Healthy").length
              : "—"}
          </dd>
        </div>
        <div className="stat-card">
          <dt>Manager verdicts recorded</dt>
          <dd>{calibration.data?.overall.total ?? "—"}</dd>
        </div>
        <div className="stat-card">
          <dt>Scoring</dt>
          <dd className="stat-card__mode">
            {providers.data?.local_only_mode ? "Local only" : "Provider chain"}
          </dd>
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
