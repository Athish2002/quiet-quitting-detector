// frontend/src/pages/History.tsx
//
// What the system has been doing, and to whom.
//
// Deliberately two separate things, not merged into one feed:
//
//   * the OPERATIONAL log -- ingests, runs, resets. Clearable, because it is
//     housekeeping.
//   * the ACCESS trail -- who looked at whose assessment. Hash-chained and
//     append-only at the database level, and there is no button here that
//     touches it.
//
// Merging them would put a "clear history" control next to the record of who
// read what about whom. That record is the answer to "would I be comfortable if
// this were run on me, and I read the audit log?" -- a UI that made it look
// erasable would undermine the one control the person being measured has.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import type { EmployeeSummary, HistoryEvent } from "../api/types";

export function History() {
  return (
    <main className="page" aria-labelledby="history-heading">
      <h1 id="history-heading">History</h1>
      <p className="page__intro">
        What has happened in this system, and how each person's assessment has
        moved over time.
      </p>
      <TrajectoriesPanel />
      <EventLogPanel />
    </main>
  );
}

function TrajectoriesPanel() {
  const { data, isPending, error } = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<EmployeeSummary[]>("/employees"),
  });

  return (
    <section aria-labelledby="trajectories-heading" className="panel">
      <h2 id="trajectories-heading">Week by week</h2>
      <p>
        Each row is one person compared against <em>their own</em> earlier weeks.
        Rows are never compared to each other.
      </p>

      {isPending ? <p role="status">Loading trajectories…</p> : null}
      {error ? <ErrorNote error={error} /> : null}
      {data && data.length === 0 ? <p>No evaluations on record yet.</p> : null}

      {data?.map((employee) => (
        <article key={employee.name} className="trajectory">
          <h3>{employee.name}</h3>
          <ol className="sparkline" aria-label={`${employee.name}'s weekly assessments`}>
            {employee.history.map((week) => (
              <li key={week.week}>
                {/* The visual bar is decorative; the text below it is the
                    accessible content, so nothing depends on seeing a shape. */}
                <span
                  className={`bar bar--${week.classification.toLowerCase().replace(/\s+/g, "-")}`}
                  style={{ height: `${week.score * 8}px` }}
                  aria-hidden="true"
                />
                <span className="sparkline__label">
                  W{week.week}: {week.classification}
                </span>
              </li>
            ))}
          </ol>
        </article>
      ))}
    </section>
  );
}

function EventLogPanel() {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const { data, isPending, error } = useQuery({
    queryKey: ["history"],
    queryFn: () => api.get<HistoryEvent[]>("/history"),
  });

  const clear = useMutation({
    mutationFn: () => api.post("/history/clear"),
    onSuccess: () => {
      setConfirming(false);
      void queryClient.invalidateQueries({ queryKey: ["history"] });
    },
  });

  return (
    <section aria-labelledby="events-heading" className="panel">
      <h2 id="events-heading">Operational event log</h2>
      <p className="hint">
        Ingests, runs and resets. This is housekeeping — it is <strong>not</strong>{" "}
        the access audit trail, which records who viewed whose assessment, is
        hash-chained, and cannot be cleared from anywhere in this interface.
      </p>

      {isPending ? <p role="status">Loading events…</p> : null}
      {error ? <ErrorNote error={error} /> : null}

      {data && data.length > 0 ? (
        <table>
          <caption>Newest first.</caption>
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">Event</th>
              <th scope="col">Detail</th>
            </tr>
          </thead>
          <tbody>
            {data.slice(0, 50).map((event, index) => (
              <tr key={index} className={event.success === false ? "row--failed" : ""}>
                <td>{event.timestamp ?? "—"}</td>
                <td>
                  {event.event_type ?? "—"}
                  {event.source ? ` / ${event.source}` : ""}
                </td>
                <td>{event.detail ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      {data && data.length === 0 ? <p>No events recorded.</p> : null}

      <div className="actions">
        {confirming ? (
          <span className="confirm">
            <span id="clear-warning">Clear the operational log?</span>
            <button
              type="button"
              className="danger"
              aria-describedby="clear-warning"
              onClick={() => clear.mutate()}
              disabled={clear.isPending}
            >
              Yes, clear it
            </button>
            <button type="button" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </span>
        ) : (
          <button type="button" onClick={() => setConfirming(true)}>
            Clear event log
          </button>
        )}
      </div>

      {clear.error ? <ErrorNote error={clear.error} /> : null}
    </section>
  );
}
