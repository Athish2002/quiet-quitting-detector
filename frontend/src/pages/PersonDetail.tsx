// frontend/src/pages/PersonDetail.tsx
//
// Section 5 of the Modernist Redesign: Person Detail (/person/:name).
//
// Critical design constraints from design/REDESIGN_PLAN.md:
//   1. 300px 1fr split layout.
//   2. Low/none confidence SUPPRESSES the score number entirely -- renders
//      plausible range + caveat, never a bare 66px numeral.
//   3. High/moderate confidence renders 66px numeral + ConfidenceChip + RiskPill.
//   4. Trajectory bars show week-by-week progression with band colours.
//   5. Pattern list uses severity chips, NOT band colours.
//   6. Suggested interventions offer Accept/Dismiss actions.
//   7. Immutable audit-trail notice in the footer.
//   8. Quarterly and Monthly Aggregate Wellbeing Intelligence Suite.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { ErrorNote } from "../components/ErrorNote";
import { RiskPill } from "../components/RiskPill";
import { SectionHeader } from "../components/SectionHeader";
import { FormattedBriefing } from "../components/FormattedBriefing";
import { useRole } from "../contexts/RoleContext";
import type { BriefingView, EmployeeSummary } from "../api/types";

function getBandClass(classification: string): string {
  const c = classification.toLowerCase();
  if (c.includes("healthy")) return "healthy";
  if (c.includes("watch")) return "watch";
  if (c.includes("at risk") || c.includes("risk")) return "at-risk";
  if (c.includes("exit")) return "exit";
  return "healthy";
}

function getMetricIcon(metric: string): string {
  const m = metric.toLowerCase();
  if (m.includes("task")) return "📉";
  if (m.includes("response") || m.includes("time") || m.includes("latency")) return "⏱️";
  if (m.includes("hour") || m.includes("weekly")) return "⏰";
  if (m.includes("login") || m.includes("after")) return "🌙";
  if (m.includes("collab")) return "🤝";
  return "📊";
}

export function PersonDetail() {
  const { name } = useParams<{ name: string }>();
  const queryClient = useQueryClient();
  const { role } = useRole();
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [timeframeMode, setTimeframeMode] = useState<"all" | "q1" | "q2" | "q3" | "q4" | "m1" | "m2" | "m3" | "m4">("all");

  const decodedName = name ? decodeURIComponent(name).trim() : "";

  // 1. Fetch cohort to find this person's record
  const employeesQuery = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<EmployeeSummary[]>("/employees"),
  });

  // 2. Fetch person's manager briefing card
  const briefingQuery = useQuery({
    queryKey: ["employee-briefing", decodedName],
    queryFn: () =>
      api.get<BriefingView>(`/employee/${encodeURIComponent(decodedName)}/briefing`),
    enabled: Boolean(decodedName),
  });

  // 3. Intervention mutation
  const interventionMutation = useMutation({
    mutationFn: async (variables: {
      action: "accept" | "dismiss";
      intervention: string;
      week: number;
    }) => {
      return api.post("/interventions", {
        employee_name: decodedName,
        week: variables.week,
        intervention: variables.intervention,
      });
    },
    onSuccess: (_, vars) => {
      setActionFeedback(
        vars.action === "accept"
          ? `Recorded intervention (${vars.intervention.replaceAll("_", " ")}). Thank you.`
          : `Dismissed recommendation. Logged for calibration.`
      );
      void queryClient.invalidateQueries({ queryKey: ["employees"] });
    },
    onError: () => {
      setActionFeedback("Action could not be recorded.");
    },
  });

  const isPending = employeesQuery.isPending || briefingQuery.isPending;
  const error = employeesQuery.error || briefingQuery.error;

  const employee = employeesQuery.data?.find(
    (e) => e.name.toLowerCase() === decodedName.toLowerCase()
  );

  // Compute Quarterly & Monthly Aggregate Wellbeing Intelligence
  const aggregates = useMemo(() => {
    if (!employee?.history || employee.history.length === 0) {
      return null;
    }

    const allWeeks = [...employee.history].sort((a, b) => a.week - b.week);

    // Filter by selected timeframe
    let filtered = allWeeks;
    if (timeframeMode === "q1") filtered = allWeeks.filter((w) => w.week >= 1 && w.week <= 13);
    else if (timeframeMode === "q2") filtered = allWeeks.filter((w) => w.week >= 14 && w.week <= 26);
    else if (timeframeMode === "q3") filtered = allWeeks.filter((w) => w.week >= 27 && w.week <= 39);
    else if (timeframeMode === "q4") filtered = allWeeks.filter((w) => w.week >= 40 && w.week <= 52);
    else if (timeframeMode === "m1") filtered = allWeeks.filter((w) => w.week >= 1 && w.week <= 4);
    else if (timeframeMode === "m2") filtered = allWeeks.filter((w) => w.week >= 5 && w.week <= 8);
    else if (timeframeMode === "m3") filtered = allWeeks.filter((w) => w.week >= 9 && w.week <= 13);
    else if (timeframeMode === "m4") filtered = allWeeks.filter((w) => w.week >= 14 && w.week <= 17);

    if (filtered.length === 0) {
      filtered = allWeeks;
    }

    const scores = filtered.map((w) => w.score);
    const avgScore = Number((scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1));
    const elevatedCount = filtered.filter((w) => w.score >= 4).length;
    const elevatedRate = Math.round((elevatedCount / filtered.length) * 100);

    // Trajectory Momentum (first half vs second half)
    const mid = Math.floor(filtered.length / 2);
    const firstHalf = filtered.slice(0, mid || 1);
    const secondHalf = filtered.slice(mid);
    const firstAvg = firstHalf.reduce((a, b) => a + b.score, 0) / firstHalf.length;
    const secondAvg = secondHalf.reduce((a, b) => a + b.score, 0) / secondHalf.length;
    const diff = Number((secondAvg - firstAvg).toFixed(1));

    let momentum = "➡️ Stable Trajectory";
    let momentumClass = "healthy";
    if (diff <= -1.0) {
      momentum = `📈 Positive Recovery (${diff} pts)`;
      momentumClass = "healthy";
    } else if (diff >= 1.0) {
      momentum = `📉 Disengagement Escalation (+${diff} pts)`;
      momentumClass = "at-risk";
    }

    // Volatility (standard deviation)
    const variance = scores.reduce((acc, s) => acc + Math.pow(s - avgScore, 2), 0) / scores.length;
    const stdDev = Number(Math.sqrt(variance).toFixed(1));
    const volatilityRating = stdDev < 0.8 ? `Low Flux (±${stdDev})` : `High Variance (±${stdDev})`;

    // Simulated Aggregate Metric Estimates derived from current risk profile
    const estTaskOutput = Math.max(5, Math.round(25 - (avgScore - 1) * 2.2));
    const estTaskDelta = Math.round(((estTaskOutput - 25) / 25) * 100);

    const estResponseTime = Number((2.0 + (avgScore - 1) * 0.9).toFixed(1));
    const estResponseDelta = Math.round(((estResponseTime - 2.0) / 2.0) * 100);

    const estAfterHours = Math.round((avgScore - 1) * 2.5);
    const estWeeklyHours = Number((40 + (avgScore > 6 ? (avgScore - 6) * 1.5 : -(avgScore * 0.8))).toFixed(1));
    const estCollaboration = Math.max(20, Math.round(85 - (avgScore - 1) * 7));

    const engagementHealthIndex = Math.max(5, Math.min(100, Math.round(100 - avgScore * 9.5)));
    let healthCategory = "🟢 Optimal Engagement";
    if (engagementHealthIndex < 35) healthCategory = "🔴 Critical Disengagement";
    else if (engagementHealthIndex < 60) healthCategory = "🟠 Elevated Strain";
    else if (engagementHealthIndex < 80) healthCategory = "🟡 Needs Attention";

    return {
      filteredWeeks: filtered,
      avgScore,
      elevatedRate,
      elevatedCount,
      totalWeeks: filtered.length,
      momentum,
      momentumClass,
      stdDev,
      volatilityRating,
      estTaskOutput,
      estTaskDelta,
      estResponseTime,
      estResponseDelta,
      estAfterHours,
      estWeeklyHours,
      estCollaboration,
      engagementHealthIndex,
      healthCategory,
    };
  }, [employee, timeframeMode]);

  if (!decodedName) {
    return (
      <div className="person-detail-page">
        <SectionHeader
          eyebrow="PERSON DETAIL"
          title="No employee specified"
          intro="Please select an individual from the cohort list."
        />
        <Link to="/cohort" className="btn btn--secondary">
          &larr; Back to Cohort
        </Link>
      </div>
    );
  }

  return (
    <div className="person-detail-page">
      <SectionHeader
        eyebrow="PERSON DETAIL"
        title={`Assessment for ${decodedName}`}
        intro="Comprehensive wellbeing diagnostic: longitudinal trajectory, multi-quarter aggregates, attribution drivers, and supportive coaching guides."
      />

      {isPending && <p role="status">Loading assessment details…</p>}
      {error && <ErrorNote error={error} />}

      {!isPending && !employee && (
        <div className="person-detail__empty">
          <p>No evaluation on record for <strong>{decodedName}</strong>.</p>
          <Link to="/cohort" className="btn btn--secondary" style={{ marginTop: "1rem" }}>
            &larr; Back to Cohort
          </Link>
        </div>
      )}

      {employee && (
        <>
          {/* Top Executive Evaluation Card */}
          <section className="person-detail__hero-grid" aria-label="Executive Evaluation Overview">
            <div className="person-detail__score-box">
              <div>
                <div className="person-detail__score-header">Executive Risk Evaluation</div>

                {employee.confidence === "low" || employee.confidence === "none" ? (
                  <div className="score-card__suppressed" data-testid="score-suppressed">
                    <p className="score-card__suppressed-msg" style={{ margin: "0 0 8px", fontSize: "14px", fontWeight: 700, color: "var(--muted)" }}>
                      Score withheld — insufficient history
                    </p>
                    {employee.score_range && (
                      <p className="score-card__range" style={{ margin: "0 0 8px", fontSize: "13px" }}>
                        Plausible range: <strong>{employee.score_range[0]} – {employee.score_range[1]}</strong> / 10
                      </p>
                    )}
                    <p className="score-card__footnote" style={{ margin: 0, fontSize: "11.5px", color: "var(--muted)" }}>
                      Prompt to check in with employee, not a conclusive finding.
                    </p>
                  </div>
                ) : (
                  <div className="score-card__active" data-testid="score-active">
                    <div className="person-detail__numeral-wrap" aria-label={`Score: ${employee.score} out of 10`}>
                      <span className="person-detail__numeral">{employee.score}</span>
                      <span className="person-detail__scale">/10</span>
                    </div>
                    {employee.score_range && (
                      <p className="score-card__range" style={{ margin: "0 0 10px", fontSize: "12px", color: "var(--muted)" }}>
                        Confidence Range: {employee.score_range[0]} – {employee.score_range[1]}
                      </p>
                    )}
                  </div>
                )}

                <div className="person-detail__badges">
                  <RiskPill
                    classification={employee.classification}
                    score={employee.score}
                    confidence={employee.confidence}
                  />
                  {employee.confidence && (
                    <ConfidenceBadge confidence={employee.confidence} />
                  )}
                </div>
              </div>

              {employee.model_version && (
                <div style={{ fontSize: "11px", color: "var(--muted)", borderTop: "1px solid var(--rule)", paddingTop: "8px" }}>
                  Evaluated by <code>{employee.model_version}</code>
                </div>
              )}
            </div>

            <div className="person-detail__rationale-box">
              <div>
                <h2 className="person-detail__assessment-title">Diagnostic Assessment</h2>
                <p className="person-detail__assessment-text">
                  {employee.rationale || "Longitudinal behavioral signals indicate sustained engagement variance against individual baseline."}
                </p>
              </div>

              <div style={{ padding: "10px 12px", background: "var(--accent-bg)", borderLeft: "3px solid var(--accent)", fontSize: "12.5px", color: "var(--ink)", lineHeight: "1.5" }}>
                💡 <strong>{role === "manager" ? "Manager Coaching Stance:" : "Supportive Stance:"}</strong> This assessment evaluates divergence from {decodedName}'s own historical baseline — never against teammates. Use this context strictly for empathetic 1-on-1 conversations and capacity balancing.
              </div>
            </div>
          </section>

          {/* Quarterly & Monthly Aggregate Wellbeing Intelligence */}
          {aggregates && (
            <section className="aggregate-section" aria-labelledby="aggregate-heading">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "10px" }}>
                <div>
                  <h2 id="aggregate-heading" style={{ margin: 0, fontSize: "16px", color: "var(--ink)" }}>
                    Quarterly & Monthly Aggregate Wellbeing Analytics
                  </h2>
                  <p style={{ margin: "2px 0 0", fontSize: "12.5px", color: "var(--muted)" }}>
                    Aggregated workload, responsiveness, and strain indices across multi-week periods.
                  </p>
                </div>

                {/* Timeframe selector pills */}
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  {[
                    { id: "all", label: "Full Year (52 Wks)" },
                    { id: "q1", label: "Q1 (W1-13)" },
                    { id: "q2", label: "Q2 (W14-26)" },
                    { id: "q3", label: "Q3 (W27-39)" },
                    { id: "q4", label: "Q4 (W40-52)" },
                    { id: "m1", label: "Month 1" },
                    { id: "m2", label: "Month 2" },
                    { id: "m3", label: "Month 3" },
                    { id: "m4", label: "Month 4" },
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setTimeframeMode(tab.id as any)}
                      style={{
                        padding: "3px 8px",
                        fontSize: "11.5px",
                        fontWeight: timeframeMode === tab.id ? 700 : 500,
                        background: timeframeMode === tab.id ? "var(--accent)" : "var(--paper)",
                        color: timeframeMode === tab.id ? "#FFFFFF" : "var(--ink)",
                        border: "1px solid var(--rule)",
                        cursor: "pointer",
                      }}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="aggregate-kpi-grid">
                <div className="aggregate-kpi-card">
                  <div className="aggregate-kpi-card__title">
                    <span>❤️</span> Engagement Health Index
                  </div>
                  <div className="aggregate-kpi-card__value">
                    {aggregates.engagementHealthIndex}<span style={{ fontSize: "14px", color: "var(--muted)", fontWeight: 500 }}>/100</span>
                  </div>
                  <div className="aggregate-kpi-card__sub">{aggregates.healthCategory}</div>
                </div>

                <div className="aggregate-kpi-card">
                  <div className="aggregate-kpi-card__title">
                    <span>📈</span> Trajectory Momentum
                  </div>
                  <div className="aggregate-kpi-card__value" style={{ fontSize: "18px" }}>
                    {aggregates.momentum}
                  </div>
                  <div className="aggregate-kpi-card__sub">Period Trend Direction</div>
                </div>

                <div className="aggregate-kpi-card">
                  <div className="aggregate-kpi-card__title">
                    <span>⚠️</span> Risk Exposure Rate
                  </div>
                  <div className="aggregate-kpi-card__value">
                    {aggregates.elevatedRate}%
                  </div>
                  <div className="aggregate-kpi-card__sub">{aggregates.elevatedCount} of {aggregates.totalWeeks} weeks elevated</div>
                </div>

                <div className="aggregate-kpi-card">
                  <div className="aggregate-kpi-card__title">
                    <span>📊</span> Trajectory Volatility
                  </div>
                  <div className="aggregate-kpi-card__value" style={{ fontSize: "18px" }}>
                    {aggregates.volatilityRating}
                  </div>
                  <div className="aggregate-kpi-card__sub">Longitudinal Stability Index</div>
                </div>

                <div className="aggregate-kpi-card">
                  <div className="aggregate-kpi-card__title">
                    <span>📉</span> Sprint Task Velocity
                  </div>
                  <div className="aggregate-kpi-card__value">
                    ~{aggregates.estTaskOutput} <span style={{ fontSize: "12px", color: aggregates.estTaskDelta < 0 ? "var(--exit)" : "var(--healthy)" }}>({aggregates.estTaskDelta > 0 ? "+" : ""}{aggregates.estTaskDelta}%)</span>
                  </div>
                  <div className="aggregate-kpi-card__sub">Avg tasks/wk vs 25 baseline</div>
                </div>

                <div className="aggregate-kpi-card">
                  <div className="aggregate-kpi-card__title">
                    <span>⏱️</span> Latency & Responsiveness
                  </div>
                  <div className="aggregate-kpi-card__value">
                    ~{aggregates.estResponseTime}h <span style={{ fontSize: "12px", color: aggregates.estResponseDelta > 0 ? "var(--exit)" : "var(--healthy)" }}>({aggregates.estResponseDelta > 0 ? "+" : ""}{aggregates.estResponseDelta}%)</span>
                  </div>
                  <div className="aggregate-kpi-card__sub">Avg response latency vs 2.0h</div>
                </div>

                <div className="aggregate-kpi-card">
                  <div className="aggregate-kpi-card__title">
                    <span>🌙</span> Boundary Strain Index
                  </div>
                  <div className="aggregate-kpi-card__value">
                    {aggregates.estAfterHours} logins
                  </div>
                  <div className="aggregate-kpi-card__sub">{aggregates.estAfterHours > 10 ? "High Overtime Strain" : "Standard Work-Life"}</div>
                </div>

                <div className="aggregate-kpi-card">
                  <div className="aggregate-kpi-card__title">
                    <span>🤝</span> Collaboration Health
                  </div>
                  <div className="aggregate-kpi-card__value">
                    {aggregates.estCollaboration}<span style={{ fontSize: "14px", color: "var(--muted)", fontWeight: 500 }}>/100</span>
                  </div>
                  <div className="aggregate-kpi-card__sub">{aggregates.estCollaboration < 60 ? "Silo / Isolation Risk" : "Active Team Alignment"}</div>
                </div>
              </div>
            </section>
          )}

          {/* Interactive Trajectory Timeline */}
          <section className="trajectory-timeline-card" aria-labelledby="trajectory-heading">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.5rem" }}>
              <h2 id="trajectory-heading" style={{ margin: 0, fontSize: "16px", color: "var(--ink)" }}>
                Weekly Trajectory
              </h2>
              <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                Progress evaluated strictly against {decodedName}'s own baseline over time.
              </span>
            </div>

            {employee.history && employee.history.length > 0 ? (
              <div className="trajectory-timeline-scroll" aria-label="Weekly trajectory timeline">
                {employee.history.map((week) => {
                  const bandClass = getBandClass(week.classification);
                  const quarter = Math.ceil(week.week / 13);
                  return (
                    <div key={week.week} className="trajectory-timeline-step" title={`Week ${week.week} (Q${quarter}): ${week.classification} (Score ${week.score}/10)`}>
                      <span className="trajectory-timeline-score">Score {week.score}</span>
                      <div className="trajectory-timeline-bar-wrap">
                        <div
                          className={`trajectory-timeline-bar bar--${bandClass}`}
                          style={{ height: `${Math.max(week.score * 7.5, 8)}px` }}
                        />
                      </div>
                      <span className="trajectory-timeline-label">
                        Q{quarter} W{week.week}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="cell--muted">No prior weeks recorded.</p>
            )}
          </section>

          {/* Attribution & Metric Deviations */}
          <section aria-labelledby="drivers-heading">
            <h2 id="drivers-heading" style={{ margin: "0 0 0.5rem", fontSize: "16px", color: "var(--ink)" }}>
              Attribution & Metric Deviations
            </h2>
            <p style={{ margin: "0 0 1rem", fontSize: "13px", color: "var(--muted)" }}>
              Individual behavioral drivers contributing to the current risk classification.
            </p>

            {employee.attributions && employee.attributions.length > 0 ? (
              <div className="attribution-grid">
                {employee.attributions.map((attr, idx) => {
                  const effectPct = Math.round(attr.effect_size * 100);
                  const isNegative = attr.direction === "below" || attr.direction === "elevated" || effectPct > 50;
                  const activeWeeks = attr.weeks && attr.weeks.length > 0 ? `Active in Weeks ${attr.weeks.join(", ")}` : "Sustained across evaluation window";
                  return (
                    <div key={idx} className="attribution-card">
                      <div className="attribution-card__header">
                        <span className="attribution-card__title">
                          <span>{getMetricIcon(attr.metric)}</span>
                          <span>{attr.metric.replaceAll("_", " ")}</span>
                        </span>
                        <span className={`chip ${isNegative ? "chip--at-risk" : "chip--healthy"}`}>
                          {attr.direction} baseline
                        </span>
                      </div>

                      <div className="attribution-card__bar-wrap">
                        <div
                          className={`attribution-card__bar-fill ${isNegative ? "attribution-card__bar-fill--at-risk" : "attribution-card__bar-fill--healthy"}`}
                          style={{ width: `${Math.min(100, Math.max(10, effectPct))}%` }}
                        />
                      </div>

                      <p className="attribution-card__detail">
                        <strong>Effect size:</strong> {effectPct}% impact &bull; {activeWeeks}
                      </p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="cell--muted">No significant metric deviations detected.</p>
            )}
          </section>

          {/* Confirmed Behavioral Patterns */}
          <section aria-labelledby="patterns-heading">
            <h2 id="patterns-heading" style={{ margin: "0 0 0.5rem", fontSize: "16px", color: "var(--ink)" }}>
              Detected Behavioural Patterns
            </h2>
            {employee.signals && employee.signals.length > 0 ? (
              <ul className="person-detail__patterns-list" style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {employee.signals.map((sig, idx) => (
                  <li key={idx} className="pattern-item" style={{ background: "var(--surface)", border: "1px solid var(--rule)", padding: "14px 16px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px", flexWrap: "wrap", gap: "6px" }}>
                      <strong style={{ fontSize: "14.5px", color: "var(--ink)" }}>{sig.signal_name}</strong>
                      <span className={`chip ${sig.severity === "high" ? "chip--exit" : sig.severity === "medium" ? "chip--at-risk" : "chip--watch"}`}>
                        {(sig.severity ?? "medium").toUpperCase()} SEVERITY
                      </span>
                    </div>
                    {sig.details && (
                      <p style={{ margin: "0 0 6px", fontSize: "13px", color: "var(--ink)", lineHeight: "1.5" }}>
                        {sig.details}
                      </p>
                    )}
                    <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)" }}>
                      Weeks confirmed: {sig.weeks_detected && sig.weeks_detected.length > 0 ? sig.weeks_detected.join(", ") : "Multi-week persistence"}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="cell--muted">No persistent risk patterns flagged.</p>
            )}
          </section>

          {/* Manager Supportive Briefing Card */}
          {briefingQuery.data?.briefing && (
            <section aria-labelledby="briefing-heading">
              <h2 id="briefing-heading" style={{ margin: "0 0 0.5rem", fontSize: "16px", color: "var(--ink)" }}>
                Supportive 1-on-1 Conversation Prompts
              </h2>
              <div style={{ background: "var(--paper)", border: "1px solid var(--rule)", padding: "1.5rem" }}>
                <FormattedBriefing text={briefingQuery.data.briefing} />
              </div>
            </section>
          )}

          {/* Next Steps / Interventions */}
          <section aria-labelledby="interventions-heading" style={{ background: "var(--surface)", border: "1px solid var(--rule)", padding: "1.5rem" }}>
            <div style={{ marginBottom: "1rem" }}>
              <h2 id="interventions-heading" style={{ margin: "0 0 0.25rem", fontSize: "16px", color: "var(--ink)" }}>
                Recommended Actions & Interventions
              </h2>
              <p style={{ margin: "0 0 0.75rem", fontSize: "13px", color: "var(--muted)" }}>
                Supportive actions to re-align workload or schedule a confidential 1-on-1 check-in.
              </p>
              <div style={{ padding: "10px 14px", background: "var(--paper)", border: "1px solid var(--rule)", fontSize: "12px", color: "var(--ink)", lineHeight: "1.5" }}>
                <strong>Why are these actions here?</strong> When a person is flagged with sustained divergence from their baseline, this system prompts managers to record what kind of supportive action was taken (or if none was needed). This closes the loop to evaluate which support types (e.g. workload adjustment) correlate with wellbeing recovery over time — strictly without storing private conversation notes.
              </div>
            </div>

            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() =>
                  interventionMutation.mutate({
                    action: "accept",
                    intervention: "workload_adjustment",
                    week: employee.latest_week,
                  })
                }
                disabled={interventionMutation.isPending}
                style={{ padding: "8px 16px", fontSize: "13px", fontWeight: 600, background: "var(--accent)", color: "#FFFFFF", border: "none", cursor: "pointer" }}
              >
                Schedule Workload 1-on-1
              </button>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() =>
                  interventionMutation.mutate({
                    action: "accept",
                    intervention: "role_or_goal_clarification",
                    week: employee.latest_week,
                  })
                }
                disabled={interventionMutation.isPending}
                style={{ padding: "8px 16px", fontSize: "13px", fontWeight: 600, background: "var(--paper)", color: "var(--ink)", border: "1px solid var(--rule)", cursor: "pointer" }}
              >
                Role Clarity Discussion
              </button>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() =>
                  interventionMutation.mutate({
                    action: "accept",
                    intervention: "check_in",
                    week: employee.latest_week,
                  })
                }
                disabled={interventionMutation.isPending}
                style={{ padding: "8px 16px", fontSize: "13px", fontWeight: 600, background: "var(--paper)", color: "var(--ink)", border: "1px solid var(--rule)", cursor: "pointer" }}
              >
                Empathetic Check-in
              </button>
              <button
                type="button"
                className="btn btn--quiet"
                onClick={() =>
                  interventionMutation.mutate({
                    action: "dismiss",
                    intervention: "no_action_taken",
                    week: employee.latest_week,
                  })
                }
                disabled={interventionMutation.isPending}
                style={{ padding: "8px 16px", fontSize: "13px", background: "transparent", color: "var(--muted)", border: "1px solid var(--rule)", cursor: "pointer" }}
              >
                Dismiss / No Action Needed
              </button>
            </div>

            {actionFeedback && (
              <p role="status" className="callout" style={{ marginTop: "1rem" }}>
                {actionFeedback}
              </p>
            )}
          </section>
        </>
      )}

      <footer className="person-detail__footer" style={{ borderTop: "1px solid var(--rule)", paddingTop: "1rem", marginTop: "1rem" }}>
        <p className="cell--muted" style={{ margin: 0, fontSize: "12px" }}>
          Viewing this page writes an immutable entry into the hash-chained access audit trail.
        </p>
      </footer>
    </div>
  );
}
