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
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import { SectionHeader } from "../components/SectionHeader";
import type { EmployeeSummary, HistoryEvent } from "../api/types";

export function History() {
  return (
    <div className="history-page">
      <SectionHeader
        eyebrow="HISTORY"
        title="Weekly trajectories and operational logs."
        intro="What has happened in this system, and how each person's assessment has moved over time."
      />
      <TrajectoriesPanel />
      <EventLogPanel />
    </div>
  );
}

function getBandClass(classification: string): string {
  const c = classification.toLowerCase();
  if (c.includes("healthy")) return "healthy";
  if (c.includes("watch")) return "watch";
  if (c.includes("at risk") || c.includes("risk")) return "at-risk";
  if (c.includes("exit")) return "exit";
  return "healthy";
}

function TrajectoriesPanel() {
  const { data, isPending, error } = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<EmployeeSummary[]>("/employees"),
  });

  return (
    <section aria-labelledby="trajectories-heading" className="history-section">
      <h2 id="trajectories-heading" className="history-section__title">
        Week by week
      </h2>
      <p className="history-section__subtitle">
        Each row is one person compared against <em>their own earlier weeks</em>. Rows are{" "}
        <em>never compared to each other</em>.
      </p>

      {isPending ? <p role="status">Loading trajectories…</p> : null}
      {error ? <ErrorNote error={error} /> : null}
      {data && data.length === 0 ? <p>No evaluations on record yet.</p> : null}

      <div className="trajectories-list">
        {data?.map((employee) => {
          const currentBand = getBandClass(employee.classification);
          return (
            <article key={employee.name} className="trajectory-row">
              <div className="trajectory-row__person">
                <h3 className="trajectory-row__name">{employee.name}</h3>
                <span className="trajectory-row__meta">Latest Week {employee.latest_week}</span>
              </div>

              <ol
                className="sparkline"
                aria-label={`${employee.name}'s weekly assessments`}
              >
                {employee.history.map((week) => {
                  const bandClass = getBandClass(week.classification);
                  return (
                    <li key={week.week} className="sparkline__step">
                      <div className="sparkline__bar-wrap">
                        <span
                          className={`bar bar--${bandClass}`}
                          style={{ height: `${Math.max(week.score * 4.6, 6)}px` }}
                          aria-hidden="true"
                        />
                      </div>
                      <span className="sparkline__label">
                        W{week.week}: {week.classification}
                      </span>
                    </li>
                  );
                })}
              </ol>

              <div className="trajectory-row__status">
                <span className={`chip chip--${currentBand}`}>
                  {employee.classification}
                </span>
                <Link
                  to={`/person/${employee.name}`}
                  className="btn btn--secondary btn--sm"
                >
                  Open &rarr;
                </Link>
              </div>
            </article>
          );
        })}
      </div>
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
    <section aria-labelledby="events-heading" className="history-section">
      <h2 id="events-heading" className="history-section__title">
        Operational event log
      </h2>
      <p className="history-section__subtitle">
        Ingests, runs and resets. This is housekeeping — it is <strong>not</strong> the
        access audit trail, which records who viewed whose assessment, is hash-chained, and
        cannot be cleared from anywhere in this interface.
      </p>

      {isPending ? <p role="status">Loading events…</p> : null}
      {error ? <ErrorNote error={error} /> : null}

      {data && data.length > 0 ? (
        <table className="modern-table">
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
                <td className="cell--mono">{event.timestamp || "—"}</td>
                <td>
                  {event.action || "—"}
                  {event.source ? ` / ${event.source}` : ""}
                </td>
                <td>{event.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      {data && data.length === 0 ? <p>No events recorded.</p> : null}

      <div className="history-actions">
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
            <button
              type="button"
              className="btn--quiet"
              onClick={() => setConfirming(false)}
            >
              Cancel
            </button>
          </span>
        ) : (
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => setConfirming(true)}
          >
            Clear event log
          </button>
        )}
      </div>

      {clear.error ? <ErrorNote error={clear.error} /> : null}
    </section>
  );
}
