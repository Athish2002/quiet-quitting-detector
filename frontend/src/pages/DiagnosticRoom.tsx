// frontend/src/pages/DiagnosticRoom.tsx
//
// First page of the Phase 6 migration, in the order §9 prescribes: "Diagnostic
// Room (highest value, shows off Phase 2-3 work)".
//
// What it exists to make visible, because these are the things a dashboard
// normally flattens away:
//
//   * calibration -- is this system actually right, and does it say so when it
//     does not know;
//   * intervention outcomes -- with the regression-to-the-mean caveat attached
//     to the number rather than in a footnote nobody reads;
//   * the feedback control -- the only way the system ever learns it was wrong.
//
// Accessibility is a requirement, not polish (§4): semantic landmarks, real
// headings, labelled controls, and status regions that announce themselves.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import type {
  CalibrationView,
  FeedbackVerdict,
  InterventionOutcomes,
} from "../api/types";

const VERDICTS: Array<{ value: FeedbackVerdict; label: string; hint: string }> = [
  { value: "accurate", label: "Accurate", hint: "This matched what I was seeing." },
  {
    value: "not_accurate",
    label: "Not accurate",
    hint: "This did not match what I was seeing.",
  },
  {
    value: "harmful",
    label: "Harmful",
    hint: "This should not have been surfaced, or it did damage.",
  },
];

export function DiagnosticRoom() {
  return (
    <main className="page" aria-labelledby="diagnostic-heading">
      <h1 id="diagnostic-heading">Diagnostic room</h1>
      <p className="page__intro">
        Whether this system is getting it right, and what has happened after
        managers acted on what it said.
      </p>
      <CalibrationPanel />
      <InterventionPanel />
      <FeedbackPanel />
    </main>
  );
}

function CalibrationPanel() {
  const { data, isPending, error } = useQuery({
    queryKey: ["calibration"],
    queryFn: () => api.get<CalibrationView>("/calibration"),
  });

  return (
    <section aria-labelledby="calibration-heading" className="panel">
      <h2 id="calibration-heading">Is this system right?</h2>

      {isPending ? <p role="status">Loading calibration…</p> : null}
      {error ? <ErrorNote error={error} /> : null}

      {data ? (
        <>
          {/* The message already says "not enough feedback to tell" when that
              is the truth. Rendering it prominently rather than as a subtitle
              is the whole point: an unvalidated system must look unvalidated. */}
          <p className="callout">{data.message}</p>

          {data.review_required ? (
            <p role="alert" className="callout callout--alert">
              This system is outside its acceptable operating range. Consider
              rolling back the active model.
            </p>
          ) : null}

          <dl className="stats">
            <div>
              <dt>Manager verdicts recorded</dt>
              <dd>{data.overall.total}</dd>
            </div>
            <div>
              <dt>Confirmed when raised above Healthy</dt>
              <dd>
                {data.overall.elevated_precision == null
                  ? "Not yet measurable"
                  : `${Math.round(data.overall.elevated_precision * 100)}%`}
              </dd>
            </div>
            <div>
              {/* Never netted off against accuracy. A tool that is 90% accurate
                  and harmful 10% of the time is not a good tool. */}
              <dt>Reported as harmful</dt>
              <dd>{data.overall.harmful}</dd>
            </div>
            <div>
              <dt>Active model</dt>
              <dd>{data.active_model_version}</dd>
            </div>
          </dl>
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
    <section aria-labelledby="intervention-heading" className="panel">
      <h2 id="intervention-heading">What happened after managers acted</h2>

      {isPending ? <p role="status">Loading outcomes…</p> : null}
      {error ? <ErrorNote error={error} /> : null}

      {data ? (
        <>
          {/* The caveat leads. Placing it after the table would let a reader
              take the numbers as causal, which they are not. */}
          <p className="callout callout--caveat">{data.caveat}</p>

          {data.by_type.length === 0 ? (
            <p>No interventions have been recorded yet.</p>
          ) : (
            <table>
              <caption>
                Recovery beyond what regression to the mean already predicts.
                Association only — not evidence of cause.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Kind of action</th>
                  <th scope="col">Measured</th>
                  <th scope="col">Improved</th>
                  <th scope="col">Declined</th>
                  <th scope="col">No detectable change</th>
                </tr>
              </thead>
              <tbody>
                {data.by_type.map((row) => (
                  <tr key={row.intervention}>
                    <th scope="row">{row.intervention.replaceAll("_", " ")}</th>
                    {row.reportable ? (
                      <>
                        <td>{row.sample_size}</td>
                        <td>{row.improved}</td>
                        <td>{row.declined}</td>
                        <td>{row.no_change}</td>
                      </>
                    ) : (
                      <td colSpan={4}>{row.note}</td>
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
    <section aria-labelledby="feedback-heading" className="panel">
      <h2 id="feedback-heading">Tell us whether a briefing was right</h2>
      <p>
        This is the only way the system finds out it was wrong. There is no free
        text field on purpose — please do not record anything about a person’s
        health or circumstances anywhere in this tool.
      </p>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <div className="field">
          <label htmlFor="fb-name">First name</label>
          <input
            id="fb-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="fb-week">Week</label>
          <input
            id="fb-week"
            type="number"
            min={1}
            value={week}
            onChange={(event) => setWeek(Number(event.target.value))}
            required
          />
        </div>

        <fieldset>
          <legend>Your verdict</legend>
          {VERDICTS.map((option) => (
            <div key={option.value} className="field field--radio">
              <input
                type="radio"
                id={`fb-${option.value}`}
                name="verdict"
                value={option.value}
                checked={verdict === option.value}
                onChange={() => setVerdict(option.value)}
              />
              <label htmlFor={`fb-${option.value}`}>
                {option.label} <span className="hint">{option.hint}</span>
              </label>
            </div>
          ))}
        </fieldset>

        <button type="submit" disabled={mutation.isPending || !name.trim()}>
          {mutation.isPending ? "Recording…" : "Record verdict"}
        </button>
      </form>

      {mutation.isSuccess ? (
        <p role="status" className="callout">
          Recorded. Thank you — this is what keeps the system honest.
        </p>
      ) : null}
      {mutation.error ? <ErrorNote error={mutation.error} /> : null}
    </section>
  );
}
