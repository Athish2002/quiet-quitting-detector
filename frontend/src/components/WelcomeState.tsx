// frontend/src/components/WelcomeState.tsx
//
// Modernist WelcomeState Component
//
// Shows a friendly welcome screen when a user first logs in and there is no data yet.
// Replaces the dashboard content until the pipeline has been run.
//
// Role-specific messaging:
// - analyst: Explains the ethical self-baseline premise, 3-step pipeline flow, and link to /ingest.
// - manager: Explains that supportive briefings will appear once analysis is run, notes it is a wellbeing prompt.
// - employee: Explains their trajectory will appear and guarantees privacy (only own data visible).

import { Link } from "react-router-dom";
import { BrandSymbol } from "./BrandSymbol";

export type Role = "analyst" | "manager" | "employee";

export interface WelcomeStateProps {
  role: Role;
}

interface StepItem {
  number: string;
  title: string;
  body: string;
}

const ANALYST_STEPS: StepItem[] = [
  {
    number: "Step 1",
    title: "Ingest data",
    body: "Upload a week of telemetry to begin. CSV, JSON, or direct database connection.",
  },
  {
    number: "Step 2",
    title: "Run the pipeline",
    body: "The system evaluates each person against their own history \u2014 never against a cohort average.",
  },
  {
    number: "Step 3",
    title: "Review the cohort",
    body: "Alphabetical and unranked. Click any person for their full assessment and manager briefing.",
  },
];

export function WelcomeState({ role }: WelcomeStateProps) {
  if (role === "manager") {
    return (
      <div className="welcome-state" role="region" aria-label="Welcome state">
        <div style={{ display: "inline-flex", marginBottom: "16px" }}>
          <BrandSymbol size={42} />
        </div>
        <h2 className="welcome-state__heading">No briefings available yet</h2>
        <p className="welcome-state__text">
          Your wellbeing team will run the analysis. Once ready, you&apos;ll see
          supportive briefings for your team members here.
        </p>
        <p className="welcome-state__note">
          This system is a wellbeing prompt, not a performance tool. Scores and
          diagnostics are not shown in this view.
        </p>
      </div>
    );
  }

  if (role === "employee") {
    return (
      <div className="welcome-state" role="region" aria-label="Welcome state">
        <div style={{ display: "inline-flex", marginBottom: "16px" }}>
          <BrandSymbol size={42} />
        </div>
        <h2 className="welcome-state__heading">Your wellbeing dashboard</h2>
        <p className="welcome-state__text">
          No self-assessment data is available yet. Once your team&apos;s
          wellbeing analysis is ready, your own trajectory will appear here.
        </p>
        <p className="welcome-state__note">
          Only your own data is visible. Nobody else&apos;s assessments are
          shown.
        </p>
      </div>
    );
  }

  // Default: analyst
  return (
    <div className="welcome-state" role="region" aria-label="Welcome state">
      <div style={{ display: "inline-flex", marginBottom: "16px" }}>
        <BrandSymbol size={46} />
      </div>
      <h2 className="welcome-state__heading">
        Welcome to the Quiet-Quitting Detector
      </h2>
      <p className="welcome-state__text">
        This system identifies sustained divergence from an employee&apos;s own
        baseline and drafts supportive manager briefings. It never ranks people
        or recommends disciplinary action.
      </p>

      <ol
        className="welcome-state__steps welcome-steps"
        aria-label="Getting started steps"
      >
        {ANALYST_STEPS.map((step) => (
          <li key={step.number} className="welcome-step">
            <span className="welcome-step__number">{step.number}</span>
            <h3 className="welcome-step__title">{step.title}</h3>
            <p className="welcome-step__body">{step.body}</p>
          </li>
        ))}
      </ol>

      <div className="welcome-state__action">
        <Link to="/ingest" className="btn btn--primary">
          Get started &rarr;
        </Link>
      </div>
    </div>
  );
}
