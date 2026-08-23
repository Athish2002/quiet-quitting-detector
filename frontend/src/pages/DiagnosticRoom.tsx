// frontend/src/pages/DiagnosticRoom.tsx
//
// Diagnostic Room: Model calibration, harm metrics, and the closed-vocabulary manager feedback form.
// Fully overhauled with the Modernist design system.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { SectionHeader } from "../components/SectionHeader";
import { ErrorNote } from "../components/ErrorNote";
import type {
  CalibrationView,
  FeedbackVerdict,
  InterventionOutcomes,
} from "../api/types";

const VERDICTS: Array<{ value: FeedbackVerdict; label: string; hint: string; icon: string }> = [
  { value: "accurate", label: "Accurate", hint: "This matched what I was seeing.", icon: "✅" },
  {
    value: "not_accurate",
    label: "Not accurate",
    hint: "This did not match what I was seeing.",
    icon: "⚠️",
  },
  {
    value: "harmful",
    label: "Harmful",
    hint: "This should not have been surfaced, or it did damage.",
    icon: "🛑",
  },
];

export function DiagnosticRoom() {
  return (
    <div className="diagnostic-page" aria-labelledby="diagnostic-heading">
      <SectionHeader
        eyebrow="DIAGNOSTIC ROOM"
        title="Whether this system is getting it right."
        intro="Model calibration, harm metrics, and the closed-vocabulary manager verdict form. The system learns and verifies its accuracy through supervisor feedback."
      />
      <div style={{ display: "flex", flexDirection: "column", gap: "2rem", marginTop: "1.5rem" }}>
        <CalibrationPanel />
        <InterventionPanel />
        <FeedbackPanel />
      </div>
    </div>
  );
}

function CalibrationPanel() {
  const { data, isPending, error } = useQuery({
    queryKey: ["calibration"],
    queryFn: () => api.get<CalibrationView>("/calibration"),
  });

  return (
    <section aria-labelledby="calibration-heading" className="panel" style={{ background: "var(--surface)", border: "1px solid var(--rule)", padding: "1.5rem" }}>
      <h2 id="calibration-heading" style={{ margin: "0 0 10px", fontSize: "18px", fontFamily: "var(--font-heading)", color: "var(--ink)" }}>
        System Precision & Calibration
      </h2>

      {isPending ? <p role="status">Loading calibration metrics…</p> : null}
      {error ? <ErrorNote error={error} /> : null}

      {data ? (
        <>
          {data.review_required ? (
            <div role="alert" className="callout" style={{ borderLeft: "4px solid var(--exit)", background: "var(--paper)", marginBottom: "1.25rem", padding: "1rem" }}>
              <strong>Operational Alert:</strong> This system is outside its optimal precision range. Reviewing active model weights recommended.
            </div>
          ) : (
            <div className="callout" style={{ borderLeft: "4px solid var(--healthy)", background: "var(--paper)", marginBottom: "1.25rem", padding: "1rem" }}>
              <p style={{ margin: 0, fontSize: "13.5px", color: "var(--ink)" }}>
                {data.message || "Active model performing within calibrated tolerance."}
              </p>
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem" }}>
            <div style={{ padding: "1rem", background: "var(--paper)", border: "1px solid var(--rule)" }}>
              <span style={{ display: "block", fontSize: "12px", letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--muted)", marginBottom: "4px" }}>
                Verdicts Recorded
              </span>
              <strong style={{ fontSize: "24px", color: "var(--ink)", fontFamily: "var(--font-heading)" }}>
                {data.overall.total}
              </strong>
            </div>

            <div style={{ padding: "1rem", background: "var(--paper)", border: "1px solid var(--rule)" }}>
              <span style={{ display: "block", fontSize: "12px", letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--muted)", marginBottom: "4px" }}>
                Confirmed Elevated
              </span>
              <strong style={{ fontSize: "24px", color: "var(--healthy)", fontFamily: "var(--font-heading)" }}>
                {data.overall.elevated_precision == null
                  ? "Calibrating"
                  : `${Math.round(data.overall.elevated_precision * 100)}%`}
              </strong>
            </div>

            <div style={{ padding: "1rem", background: "var(--paper)", border: "1px solid var(--rule)" }}>
              <span style={{ display: "block", fontSize: "12px", letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--muted)", marginBottom: "4px" }}>
                Reported Harmful
              </span>
              <strong style={{ fontSize: "24px", color: data.overall.harmful > 0 ? "var(--exit)" : "var(--ink)", fontFamily: "var(--font-heading)" }}>
                {data.overall.harmful}
              </strong>
            </div>

            <div style={{ padding: "1rem", background: "var(--paper)", border: "1px solid var(--rule)" }}>
              <span style={{ display: "block", fontSize: "12px", letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--muted)", marginBottom: "4px" }}>
                Active Model
              </span>
              <strong style={{ fontSize: "15px", color: "var(--ink)", display: "block", marginTop: "6px" }}>
                <code>{data.active_model_version}</code>
              </strong>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

function InterventionPanel() {
  const { data, isPending, error } = useQuery({
    queryKey: ["intervention-outcomes"],
    queryFn: () => api.get<InterventionOutcomes>("/interventions/outcomes"),
  });

  return (
    <section aria-labelledby="intervention-heading" className="panel" style={{ background: "var(--surface)", border: "1px solid var(--rule)", padding: "1.5rem" }}>
      <h2 id="intervention-heading" style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "var(--font-heading)", color: "var(--ink)" }}>
        What Happened After Managers Acted
      </h2>
      <p style={{ margin: "0 0 1.25rem", fontSize: "13px", color: "var(--muted)" }}>
        Measurable recovery and pacing changes across recorded supportive interventions.
      </p>

      {isPending ? <p role="status">Loading outcomes…</p> : null}
      {error ? <ErrorNote error={error} /> : null}

      {data ? (
        <>
          <div className="callout callout--caveat" style={{ borderLeft: "4px solid var(--accent)", background: "var(--paper)", marginBottom: "1rem", padding: "0.75rem 1rem", fontSize: "13px" }}>
            {data.caveat}
          </div>

          {data.by_type.length === 0 ? (
            <p style={{ fontSize: "13px", color: "var(--muted)" }}>No interventions recorded yet.</p>
          ) : (
            <table className="modern-table">
              <caption style={{ textAlign: "left", captionSide: "top", marginBottom: "8px", fontSize: "12px", color: "var(--muted)" }}>
                Recovery beyond what regression to the mean already predicts. Association only — not evidence of cause.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Action Type</th>
                  <th scope="col">Sample Size</th>
                  <th scope="col">Improved</th>
                  <th scope="col">Declined</th>
                  <th scope="col">No Change</th>
                </tr>
              </thead>
              <tbody>
                {data.by_type.map((row) => (
                  <tr key={row.intervention}>
                    <td>
                      <strong>{row.intervention.replaceAll("_", " ")}</strong>
                    </td>
                    {row.reportable ? (
                      <>
                        <td>{row.sample_size}</td>
                        <td style={{ color: "var(--healthy)", fontWeight: 600 }}>{row.improved}</td>
                        <td style={{ color: "var(--exit)" }}>{row.declined}</td>
                        <td style={{ color: "var(--muted)" }}>{row.no_change}</td>
                      </>
                    ) : (
                      <td colSpan={4} style={{ fontStyle: "italic", color: "var(--muted)" }}>
                        {row.note}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : null}
    </section>
  );
}

function FeedbackPanel() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [week, setWeek] = useState(1);
  const [verdict, setVerdict] = useState<FeedbackVerdict>("accurate");

  const mutation = useMutation({
    mutationFn: () =>
      api.post("/feedback", { employee_name: name, week, verdict }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["calibration"] });
    },
  });

  return (
    <section aria-labelledby="feedback-heading" className="panel" style={{ background: "var(--surface)", border: "1px solid var(--rule)", padding: "1.5rem" }}>
      <h2 id="feedback-heading" style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "var(--font-heading)", color: "var(--ink)" }}>
        Tell Us Whether a Briefing Was Right
      </h2>
      <p style={{ margin: "0 0 1.25rem", fontSize: "13px", color: "var(--muted)" }}>
        Closed-vocabulary feedback loop. Strict privacy constraint: no free-text fields to prevent health or subjective remarks.
      </p>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
        style={{ display: "flex", flexDirection: "column", gap: "1.25rem", maxWidth: "640px" }}
      >
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <div>
            <label htmlFor="fb-name" style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px", color: "var(--ink)" }}>
              First Name
            </label>
            <input
              id="fb-name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              style={{ width: "100%", padding: "8px 10px", border: "1px solid var(--rule)", background: "var(--paper)", color: "var(--ink)" }}
              required
            />
          </div>

          <div>
            <label htmlFor="fb-week" style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px", color: "var(--ink)" }}>
              Week Number
            </label>
            <input
              id="fb-week"
              type="number"
              min={1}
              value={week}
              onChange={(event) => setWeek(Number(event.target.value))}
              style={{ width: "100%", padding: "8px 10px", border: "1px solid var(--rule)", background: "var(--paper)", color: "var(--ink)" }}
              required
            />
          </div>
        </div>

        <fieldset style={{ border: "1px solid var(--rule)", padding: "1rem", background: "var(--paper)" }}>
          <legend style={{ fontSize: "12px", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)", padding: "0 6px" }}>
            Your Verdict
          </legend>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "4px" }}>
            {VERDICTS.map((option) => (
              <label
                key={option.value}
                htmlFor={`fb-${option.value}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  padding: "8px 12px",
                  border: "1px solid",
                  borderColor: verdict === option.value ? "var(--accent)" : "var(--rule)",
                  background: verdict === option.value ? "var(--accent-bg)" : "transparent",
                  cursor: "pointer",
                }}
              >
                <input
                  type="radio"
                  id={`fb-${option.value}`}
                  name="verdict"
                  value={option.value}
                  checked={verdict === option.value}
                  onChange={() => setVerdict(option.value)}
                  style={{ accentColor: "var(--accent)" }}
                />
                <div style={{ display: "flex", flexDirection: "column" }}>
                  <span style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--ink)" }}>
                    {option.icon} {option.label}
                  </span>
                  <span style={{ fontSize: "12px", color: "var(--muted)" }}>{option.hint}</span>
                </div>
              </label>
            ))}
          </div>
        </fieldset>

        <button
          type="submit"
          className="btn btn--primary"
          disabled={mutation.isPending || !name.trim()}
          style={{ padding: "10px 16px", fontWeight: 600, alignSelf: "flex-start", background: "var(--accent)", color: "#FFFFFF", border: "none", cursor: "pointer" }}
        >
          {mutation.isPending ? "Recording…" : "Record Verdict"}
        </button>
      </form>

      {mutation.isSuccess ? (
        <div role="status" className="callout" style={{ borderLeft: "4px solid var(--healthy)", background: "var(--accent-bg)", marginTop: "1rem", padding: "10px 14px", fontSize: "13px" }}>
          Verdict successfully recorded in calibration database.
        </div>
      ) : null}
      {mutation.error ? <ErrorNote error={mutation.error} /> : null}
    </section>
  );
}
