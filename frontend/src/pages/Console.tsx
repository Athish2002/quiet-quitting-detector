// frontend/src/pages/Console.tsx
//
// Second page of the Phase 6 migration. Three panels matching the original
// dashboard's structure (§4): Registry, Ingest, Simulator.
//
// Two things this page must not do, both easy to get wrong in a "control panel"
// layout:
//
//   * present the cohort as a ranking. The registry is sorted ALPHABETICALLY,
//     never by score. Sorting people by risk turns a wellbeing tool into a
//     leaderboard, and the sort control is the feature that would do it -- so
//     there isn't one.
//   * let a destructive action be one accidental click. Regenerating the demo
//     cohort deletes every stored evaluation, so it asks first.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import { RiskPill } from "../components/RiskPill";
import type { EmployeeSummary, RunProgress } from "../api/types";

export function Console() {
  return (
    <main className="page" aria-labelledby="console-heading">
      <h1 id="console-heading">Console</h1>
      <p className="page__intro">
        Who is on record, how data gets in, and a scratchpad for trying a
        scenario without touching anyone's real history.
      </p>
      <RegistryPanel />
      <IngestPanel />
      <SimulatorPanel />
    </main>
  );
}

function RegistryPanel() {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const { data, isPending, error } = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<EmployeeSummary[]>("/employees"),
  });

  const { data: progress } = useQuery({
    queryKey: ["run-progress"],
    queryFn: () => api.get<RunProgress>("/run/progress"),
    // Only poll while something is running, and not aggressively. A 1.5s poll
    // is 40 requests a minute from one idle tab, which on its own exceeded the
    // read budget and 429'd the rest of the page.
    refetchInterval: (query) => (query.state.data?.running ? 3000 : false),
  });

  const run = useMutation({
    mutationFn: () => api.post("/run"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["run-progress"] });
    },
  });

  const regenerate = useMutation({
    mutationFn: () => api.post("/mock-data"),
    onSuccess: () => {
      setConfirming(false);
      void queryClient.invalidateQueries({ queryKey: ["employees"] });
    },
  });

  return (
    <section aria-labelledby="registry-heading" className="panel">
      <h2 id="registry-heading">Registry</h2>

      {isPending ? <p role="status">Loading the cohort…</p> : null}
      {error ? <ErrorNote error={error} /> : null}

      {progress?.running ? (
        <p role="status" className="callout">
          Evaluating {progress.current ?? "…"} — {progress.done} of{" "}
          {progress.total}.
        </p>
      ) : null}
      {progress?.error ? (
        <p role="alert" className="callout callout--alert">
          The last run did not finish.
        </p>
      ) : null}

      {data && data.length === 0 ? (
        <p>Nobody on record yet. Ingest some data, then run the pipeline.</p>
      ) : null}

      {data && data.length > 0 ? (
        <table>
          {/* Alphabetical, and there is deliberately no way to sort by score. */}
          <caption>
            Listed alphabetically. This is not a ranking, and cannot be sorted
            into one.
          </caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Latest week</th>
              <th scope="col">Assessment</th>
              <th scope="col">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {data.map((employee) => (
              <tr key={employee.name}>
                <th scope="row">{employee.name}</th>
                <td>{employee.latest_week}</td>
                <td>
                  <RiskPill
                    classification={employee.classification}
                    score={employee.score}
                    confidence={employee.confidence}
                  />
                </td>
                <td>
                  {employee.confidence ?? "not recorded"}
                  {employee.degraded ? " (degraded tier)" : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      <div className="actions">
        <button type="button" onClick={() => run.mutate()} disabled={run.isPending || progress?.running}>
          {progress?.running ? "Run in progress…" : "Run the pipeline"}
        </button>

        {confirming ? (
          <span className="confirm">
            <span id="regen-warning">
              This deletes every stored evaluation. Sure?
            </span>
            <button
              type="button"
              className="danger"
              aria-describedby="regen-warning"
              onClick={() => regenerate.mutate()}
              disabled={regenerate.isPending}
            >
              Yes, regenerate
            </button>
            {/* Quiet on purpose: two filled buttons side by side make the
                reader stop and read both, and the one that deletes every
                stored evaluation should be the only one drawing the eye. */}
            <button
              type="button"
              className="btn--quiet"
              onClick={() => setConfirming(false)}
            >
              Cancel
            </button>
          </span>
        ) : (
          <button type="button" onClick={() => setConfirming(true)}>
            Regenerate demo data
          </button>
        )}
      </div>

      {run.error ? <ErrorNote error={run.error} /> : null}
      {regenerate.error ? <ErrorNote error={regenerate.error} /> : null}
    </section>
  );
}

function IngestPanel() {
  const queryClient = useQueryClient();
  const [week, setWeek] = useState(1);
  const [csv, setCsv] = useState("");

  const ingest = useMutation({
    mutationFn: () =>
      api.post("/ingest/raw", { week_number: week, csv_content: csv }),
    onSuccess: () => {
      setCsv("");
      void queryClient.invalidateQueries({ queryKey: ["employees"] });
    },
  });

  return (
    <section aria-labelledby="ingest-heading" className="panel">
      <h2 id="ingest-heading">Ingest</h2>
      <p>
        Paste a weekly export. Unknown column names are resolved by alias, and
        re-pasting someone replaces their row rather than duplicating it. Columns
        this system is not allowed to hold — anything about health, sentiment or
        performance ratings — are dropped on the way in.
      </p>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          ingest.mutate();
        }}
      >
        <div className="field">
          <label htmlFor="ingest-week">Default week</label>
          <input
            id="ingest-week"
            type="number"
            min={1}
            value={week}
            onChange={(event) => setWeek(Number(event.target.value))}
            required
          />
          <p className="hint">
            Used for rows that do not carry their own week column.
          </p>
        </div>

        <div className="field">
          <label htmlFor="ingest-csv">CSV content</label>
          <textarea
            id="ingest-csv"
            rows={6}
            value={csv}
            onChange={(event) => setCsv(event.target.value)}
            placeholder="employee_name,tasks_completed,avg_response_time_hours,after_hours_logins,weekly_hours"
            required
          />
        </div>

        <button type="submit" disabled={ingest.isPending || !csv.trim()}>
          {ingest.isPending ? "Ingesting…" : "Ingest"}
        </button>
      </form>

      {ingest.isSuccess ? (
        <p role="status" className="callout">
          Ingested. Run the pipeline to evaluate the new data.
        </p>
      ) : null}
      {ingest.error ? <ErrorNote error={ingest.error} /> : null}
    </section>
  );
}

interface SimulationResult {
  employee_name: string;
  signals: Array<{ signal_name?: string; signal?: string; severity?: string }>;
  risk_data: { score?: number; classification?: string; rationale?: string };
  briefing: string;
}

function SimulatorPanel() {
  const [form, setForm] = useState({
    name: "Sam",
    week_number: 4,
    tasks_completed: 6,
    avg_response_time: 2.5,
    after_hours_logins: 0,
    weekly_hours: 32,
  });

  const simulate = useMutation({
    mutationFn: () => api.post<SimulationResult>("/score/custom", form),
  });

  const update = (key: keyof typeof form) => (value: number | string) =>
    setForm((current) => ({ ...current, [key]: value }));

  return (
    <section aria-labelledby="simulator-heading" className="panel">
      <h2 id="simulator-heading">Simulator</h2>
      <p>
        Runs the real agent chain against numbers you make up. Writes to a
        scratch directory, so it can never overwrite a real person's history even
        if you use their name.
      </p>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          simulate.mutate();
        }}
      >
        <div className="field">
          <label htmlFor="sim-name">First name</label>
          <input
            id="sim-name"
            value={form.name}
            onChange={(event) => update("name")(event.target.value)}
            required
          />
        </div>

        {(
          [
            ["sim-week", "Week", "week_number", 1],
            ["sim-tasks", "Tasks completed", "tasks_completed", 0],
            ["sim-response", "Average response time (hours)", "avg_response_time", 0],
            ["sim-after", "After-hours logins", "after_hours_logins", 0],
            ["sim-hours", "Weekly hours", "weekly_hours", 0],
          ] as const
        ).map(([id, label, key, min]) => (
          <div className="field" key={id}>
            <label htmlFor={id}>{label}</label>
            <input
              id={id}
              type="number"
              min={min}
              step={key === "avg_response_time" ? "0.1" : "1"}
              value={form[key]}
              onChange={(event) => update(key)(Number(event.target.value))}
              required
            />
          </div>
        ))}

        <button type="submit" disabled={simulate.isPending}>
          {simulate.isPending ? "Evaluating…" : "Evaluate"}
        </button>
      </form>

      {simulate.error ? <ErrorNote error={simulate.error} /> : null}

      {simulate.data ? (
        <div className="result" role="status">
          <h3>Result for {simulate.data.employee_name}</h3>
          <p>
            <strong>{simulate.data.risk_data.classification}</strong> —{" "}
            {simulate.data.risk_data.rationale}
          </p>
          {simulate.data.signals.length > 0 ? (
            <ul>
              {simulate.data.signals.map((signal, index) => (
                <li key={index}>
                  {signal.signal_name ?? signal.signal}
                  {signal.severity ? ` (${signal.severity})` : null}
                </li>
              ))}
            </ul>
          ) : (
            <p>No confirmed patterns.</p>
          )}
          <details>
            <summary>Manager briefing</summary>
            {/* Rendered as text, never as HTML. Model output must not become
                markup: the original dashboard had stored-XSS protections for
                exactly this and they are not worth re-earning. */}
            <pre className="briefing">{simulate.data.briefing}</pre>
          </details>
        </div>
      ) : null}
    </section>
  );
}

export { ApiError };
