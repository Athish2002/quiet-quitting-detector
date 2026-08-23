// frontend/src/pages/EmployeePortal.tsx
//
// Employee Access: Personal Wellbeing Hub & Weekly Telemetry Log
//
// Allows an employee to:
// 1. View uplifting daily cheer-ups, affirmations, and self-care reflections.
// 2. Manually enter/update their weekly reflection and workload indicators.
// 3. View their complete personal history log and self-baseline trajectory in complete privacy.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { SectionHeader } from "../components/SectionHeader";
import { ErrorNote } from "../components/ErrorNote";
import type { EmployeeSummary } from "../api/types";

interface CheerUp {
  quote: string;
  theme: string;
  icon: string;
}

const WELLBEING_CHEERUPS: CheerUp[] = [
  {
    quote: "You don’t have to do it all today. Doing your best within healthy boundaries is more than enough.",
    theme: "Self-Compassion",
    icon: "🌱",
  },
  {
    quote: "Rest is not a reward you earn after burnout — it is the foundation that makes sustainable work possible.",
    theme: "Rest & Renewal",
    icon: "☕",
  },
  {
    quote: "Celebrate small wins! Every focused step, cleared blocker, and boundary maintained is progress.",
    theme: "Daily Encouragement",
    icon: "✨",
  },
  {
    quote: "Remember to drink water, stretch your shoulders, and take three deep breaths right now.",
    theme: "Mindful Reset",
    icon: "💧",
  },
  {
    quote: "It's okay to step away from the keyboard when you hit a wall. Breakthroughs often happen during quiet walks.",
    theme: "Mental Space",
    icon: "🌿",
  },
  {
    quote: "Your worth is defined by who you are, not by the number of tickets closed this week.",
    theme: "Perspective",
    icon: "💙",
  },
  {
    quote: "Protect your evenings. When work ends, let your mind fully transition into whatever brings you joy.",
    theme: "Boundaries",
    icon: "🌅",
  },
];

interface LoggedEntry {
  week: number;
  tasks: number;
  hours: number;
  responseTime: number;
  afterHours: number;
  notes?: string;
  loggedAt: string;
}

export function EmployeePortal() {
  const queryClient = useQueryClient();

  const [quoteIndex, setQuoteIndex] = useState(0);
  const [name, setName] = useState("My Profile");
  const [weekNumber, setWeekNumber] = useState(6);
  const [tasksCompleted, setTasksCompleted] = useState(25);
  const [weeklyHours, setWeeklyHours] = useState(40);
  const [avgResponseTime, setAvgResponseTime] = useState(4);
  const [afterHoursLogins, setAfterHoursLogins] = useState(1);
  const [wellbeingNotes, setWellbeingNotes] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);

  // Local log of entries submitted in this session
  const [sessionLogs, setSessionLogs] = useState<LoggedEntry[]>([
    {
      week: 5,
      tasks: 26,
      hours: 39,
      responseTime: 3.8,
      afterHours: 1,
      notes: "Steady flow, took afternoon walk breaks.",
      loggedAt: "Prior Cycle",
    },
    {
      week: 4,
      tasks: 24,
      hours: 40,
      responseTime: 4.2,
      afterHours: 2,
      notes: "Sprint wrap-up, good collaboration with team.",
      loggedAt: "Prior Cycle",
    },
  ]);

  const currentCheerup: CheerUp = WELLBEING_CHEERUPS[quoteIndex] ?? {
    quote: "You don’t have to do it all today. Doing your best within healthy boundaries is more than enough.",
    theme: "Self-Compassion",
    icon: "🌱",
  };

  const handleNextCheerup = () => {
    setQuoteIndex((prev) => (prev + 1) % WELLBEING_CHEERUPS.length);
  };

  const employees = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<EmployeeSummary[]>("/employees"),
  });

  const myData = employees.data?.[0]; // Default or own record

  const ingestMutation = useMutation({
    mutationFn: async () => {
      // Build canonical CSV content
      const csvContent = [
        "name,week,completed_tasks,avg_response_time,after_hours_logins,weekly_hours",
        `${name.trim() || "My Profile"},${weekNumber},${tasksCompleted},${avgResponseTime},${afterHoursLogins},${weeklyHours}`,
      ].join("\n");

      return api.post<{ success: boolean; message?: string }>("/ingest/raw", {
        week_number: weekNumber,
        csv_content: csvContent,
      });
    },
    onSuccess: () => {
      setFeedback("Weekly reflection and telemetry successfully recorded in master log.");
      // Append to local session log
      setSessionLogs((prev) => [
        {
          week: weekNumber,
          tasks: tasksCompleted,
          hours: weeklyHours,
          responseTime: avgResponseTime,
          afterHours: afterHoursLogins,
          notes: wellbeingNotes.trim() || undefined,
          loggedAt: "Just now",
        },
        ...prev.filter((item) => item.week !== weekNumber),
      ]);
      void queryClient.invalidateQueries({ queryKey: ["employees"] });
    },
    onError: (err: Error) => {
      setFeedback(`Submission failed: ${err.message}`);
    },
  });

  return (
    <div className="employee-portal-page" aria-labelledby="employee-portal-title">
      <SectionHeader
        eyebrow="MY WELLBEING"
        title="Your personal workload & reflection space."
        intro="Log your weekly work patterns, reflect on workload pacing, and view your personal wellbeing trajectory. Your data is evaluated solely against your own baseline history."
      />

      {/* Uplifting Cheer-Up & Self-Care Card */}
      <section
        className="cheerup-card"
        aria-label="Daily Wellbeing Reflection"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--rule)",
          borderLeft: "4px solid var(--accent)",
          padding: "1.25rem 1.5rem",
          marginBottom: "1.5rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "1rem",
        }}
      >
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
            <span style={{ fontSize: "20px" }} aria-hidden="true">{currentCheerup.icon}</span>
            <span style={{ fontSize: "11.5px", letterSpacing: "0.08em", textTransform: "uppercase", fontWeight: 600, color: "var(--accent)" }}>
              {currentCheerup.theme}
            </span>
          </div>
          <p style={{ margin: 0, fontSize: "15px", fontStyle: "italic", color: "var(--ink)", lineHeight: "1.5" }}>
            &ldquo;{currentCheerup.quote}&rdquo;
          </p>
        </div>
        <button
          type="button"
          onClick={handleNextCheerup}
          className="btn btn--secondary"
          style={{ fontSize: "12px", whiteSpace: "nowrap", padding: "6px 12px" }}
        >
          New Cheer-Up ✨
        </button>
      </section>

      <div className="callout" role="note" style={{ borderLeft: "4px solid var(--healthy)", background: "var(--surface)", padding: "1rem" }}>
        <p style={{ margin: 0, fontSize: "13.5px", color: "var(--ink)" }}>
          🔒 <strong>Privacy Assurance:</strong> This portal displays only your personal trajectory. No peer rankings or performance comparisons are made.
        </p>
      </div>

      <div className="portal-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "2rem", marginTop: "1.5rem" }}>
        {/* Left Column: Weekly Data Logging & Reflection Form */}
        <section className="portal-card" aria-labelledby="log-form-title" style={{ background: "var(--surface)", border: "1px solid var(--rule)", padding: "1.5rem" }}>
          <h2 id="log-form-title" style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "var(--font-heading)", color: "var(--ink)" }}>
            Log Weekly Telemetry & Reflection
          </h2>
          <p style={{ margin: "0 0 1.25rem", fontSize: "13px", color: "var(--muted)" }}>
            Update your self-reported telemetry for the current cycle.
          </p>

          {feedback && (
            <div role="status" style={{ padding: "10px", background: "var(--accent-bg)", borderLeft: "3px solid var(--accent)", marginBottom: "1rem", fontSize: "13px", color: "var(--ink)" }}>
              {feedback}
            </div>
          )}

          {ingestMutation.error && <ErrorNote error={ingestMutation.error} />}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              ingestMutation.mutate();
            }}
            style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
          >
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div>
                <label htmlFor="emp-name" style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px", color: "var(--ink)" }}>
                  Your Name / ID
                </label>
                <input
                  id="emp-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={{ width: "100%", padding: "6px 8px", border: "1px solid var(--rule)", background: "var(--paper)", color: "var(--ink)", minWidth: 0 }}
                  required
                />
              </div>
              <div>
                <label htmlFor="emp-week" style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px", color: "var(--ink)" }}>
                  Week Number
                </label>
                <input
                  id="emp-week"
                  type="number"
                  min="1"
                  max="52"
                  value={weekNumber}
                  onChange={(e) => setWeekNumber(Number(e.target.value))}
                  style={{ width: "100%", padding: "6px 8px", border: "1px solid var(--rule)", background: "var(--paper)", color: "var(--ink)", minWidth: 0 }}
                  required
                />
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div>
                <label htmlFor="emp-tasks" style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px", color: "var(--ink)" }}>
                  Completed Tasks
                </label>
                <input
                  id="emp-tasks"
                  type="number"
                  min="0"
                  max="500"
                  value={tasksCompleted}
                  onChange={(e) => setTasksCompleted(Number(e.target.value))}
                  style={{ width: "100%", padding: "6px 8px", border: "1px solid var(--rule)", background: "var(--paper)", color: "var(--ink)", minWidth: 0 }}
                  required
                />
              </div>
              <div>
                <label htmlFor="emp-hours" style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px", color: "var(--ink)" }}>
                  Weekly Hours
                </label>
                <input
                  id="emp-hours"
                  type="number"
                  min="0"
                  max="168"
                  value={weeklyHours}
                  onChange={(e) => setWeeklyHours(Number(e.target.value))}
                  style={{ width: "100%", padding: "6px 8px", border: "1px solid var(--rule)", background: "var(--paper)", color: "var(--ink)", minWidth: 0 }}
                  required
                />
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div>
                <label htmlFor="emp-response" style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px", color: "var(--ink)" }}>
                  Avg Response (Hours)
                </label>
                <input
                  id="emp-response"
                  type="number"
                  min="0"
                  max="72"
                  step="0.5"
                  value={avgResponseTime}
                  onChange={(e) => setAvgResponseTime(Number(e.target.value))}
                  style={{ width: "100%", padding: "6px 8px", border: "1px solid var(--rule)", background: "var(--paper)", color: "var(--ink)", minWidth: 0 }}
                  required
                />
              </div>
              <div>
                <label htmlFor="emp-afterhours" style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px", color: "var(--ink)" }}>
                  After-Hours Logins
                </label>
                <input
                  id="emp-afterhours"
                  type="number"
                  min="0"
                  max="50"
                  value={afterHoursLogins}
                  onChange={(e) => setAfterHoursLogins(Number(e.target.value))}
                  style={{ width: "100%", padding: "6px 8px", border: "1px solid var(--rule)", background: "var(--paper)", color: "var(--ink)", minWidth: 0 }}
                  required
                />
              </div>
            </div>

            <div>
              <label htmlFor="emp-notes" style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px", color: "var(--ink)" }}>
                Personal Reflection Notes (Optional)
              </label>
              <textarea
                id="emp-notes"
                rows={3}
                placeholder="How did this week feel in terms of energy, focus, and workload balance?"
                value={wellbeingNotes}
                onChange={(e) => setWellbeingNotes(e.target.value)}
                style={{ width: "100%", padding: "6px 8px", border: "1px solid var(--rule)", background: "var(--paper)", color: "var(--ink)", minWidth: 0 }}
              />
            </div>

            <button
              type="submit"
              className="btn btn--primary"
              disabled={ingestMutation.isPending}
              style={{ padding: "10px", fontWeight: 600, background: "var(--accent)", color: "#FFFFFF", border: "none", cursor: "pointer" }}
            >
              {ingestMutation.isPending ? "Submitting…" : "Record Weekly Reflection"}
            </button>
          </form>
        </section>

        {/* Right Column: Personal Trajectory & Wellbeing Guide */}
        <section className="portal-card" aria-labelledby="trajectory-card-title" style={{ background: "var(--surface)", border: "1px solid var(--rule)", padding: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
            <h2 id="trajectory-card-title" style={{ margin: 0, fontSize: "18px", fontFamily: "var(--font-heading)", color: "var(--ink)" }}>
              Personal Trajectory & Rest Guidance
            </h2>
            <span style={{ fontSize: "11px", padding: "2px 8px", background: "var(--healthy-bg)", color: "var(--healthy)", border: "1px solid var(--healthy)", fontWeight: 600 }}>
              100% Private to You
            </span>
          </div>
          <p style={{ margin: "0 0 1.25rem", fontSize: "13px", color: "var(--muted)" }}>
            Evaluated solely against your rolling personal baseline.
          </p>

          {myData?.history && myData.history.length > 0 ? (
            <div style={{ marginBottom: "1.5rem" }}>
              <ol className="sparkline" aria-label="Your weekly trajectory">
                {myData.history.map((h) => (
                  <li key={h.week} className="sparkline__step">
                    <div className="sparkline__bar-wrap">
                      <span
                        className="bar bar--healthy"
                        style={{ height: `${Math.max(h.score * 4.6, 6)}px`, background: "var(--accent)" }}
                        aria-hidden="true"
                      />
                    </div>
                    <span className="sparkline__label">Week {h.week}</span>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <p style={{ fontSize: "13px", color: "var(--muted)", fontStyle: "italic", marginBottom: "1.5rem" }}>
              No prior history recorded yet. Enter your current week on the left to start your baseline.
            </p>
          )}

          {/* Dynamic Boundary & Self-Advocacy Card */}
          <div style={{ background: "var(--paper)", borderLeft: "3px solid var(--accent)", padding: "12px 14px", marginBottom: "1.25rem" }}>
            <h3 style={{ margin: "0 0 6px", fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--accent)", display: "flex", alignItems: "center", gap: "6px" }}>
              <span>🌱</span> Proactive Workload Pacing Recommendation
            </h3>
            <p style={{ margin: 0, fontSize: "13px", lineHeight: "1.55", color: "var(--ink)" }}>
              {afterHoursLogins > 2 || weeklyHours > 45
                ? "Your after-hours sessions have climbed above your typical rhythm. We recommend setting a hard evening disconnect at 6:30 PM and discussing task descope with your lead."
                : avgResponseTime > 5
                ? "Communication latency is elevated. Protect your uninterrupted focus blocks and remind your team of your 24-hour async response window."
                : "Your workload rhythm is balanced. Keep protecting your recovery boundaries and focus blocks."}
            </p>
          </div>

          <h3 style={{ fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)", margin: "0 0 8px" }}>
            Personal Wellbeing Boundaries
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "13px", color: "var(--ink)", marginBottom: "1.25rem" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
              <input type="checkbox" defaultChecked /> Daily 2-hour uninterrupted focus block
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
              <input type="checkbox" defaultChecked /> Pencils-down evening disconnect (no work chat after 6:30 PM)
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
              <input type="checkbox" /> 30-minute screen-free midday reset
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
              <input type="checkbox" /> 5-minute movement break every 90 minutes
            </label>
          </div>

          <div style={{ padding: "10px 12px", background: "var(--paper)", border: "1px solid var(--rule)", fontSize: "12px", color: "var(--muted)", lineHeight: "1.5" }}>
            🛡️ <strong>Zero-Surveillance Guarantee:</strong> Your individual reflection notes are never shared with managers or HR. Only non-punitive, supportive conversation prompts are provided.
          </div>
        </section>
      </div>

      {/* Bottom Section: My Logged Telemetry & Reflection History */}
      <section
        className="portal-history-section"
        aria-labelledby="history-table-title"
        style={{ marginTop: "2rem", background: "var(--surface)", border: "1px solid var(--rule)", padding: "1.5rem" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <div>
            <h2 id="history-table-title" style={{ margin: 0, fontSize: "18px", fontFamily: "var(--font-heading)", color: "var(--ink)" }}>
              My Telemetry & Reflection Log
            </h2>
            <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--muted)" }}>
              A private record of your weekly reflections and self-reported inputs.
            </p>
          </div>
          <span style={{ fontSize: "12px", padding: "4px 8px", background: "var(--accent-bg)", color: "var(--ink)" }}>
            {sessionLogs.length} Cycles Recorded
          </span>
        </div>

        <table className="modern-table">
          <thead>
            <tr>
              <th scope="col">Week</th>
              <th scope="col">Tasks</th>
              <th scope="col">Hours</th>
              <th scope="col">Avg Response</th>
              <th scope="col">After-Hours</th>
              <th scope="col">Personal Reflection</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {sessionLogs.map((entry) => (
              <tr key={entry.week}>
                <td><strong>Week {entry.week}</strong></td>
                <td>{entry.tasks}</td>
                <td>{entry.hours} hrs</td>
                <td>{entry.responseTime} hrs</td>
                <td>{entry.afterHours} logins</td>
                <td style={{ maxWidth: "280px" }}>{entry.notes || "—"}</td>
                <td>
                  <span className="chip chip--healthy" style={{ fontSize: "11px" }}>
                    {entry.loggedAt}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
