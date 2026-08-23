// frontend/src/pages/ManagerBriefings.tsx
//
// Manager Access: Supportive Mental Wellbeing Briefings
//
// Designed exclusively for managers to conduct constructive, compassionate 1-on-1
// wellbeing check-ins. It explicitly strips performance evaluation framing and focuses
// on:
// - Mental wellbeing & sustained overwork indicators
// - Supportive conversation starters
// - Actionable workload rebalancing recommendations
// - Clear non-punitive ethical guardrails

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { SectionHeader } from "../components/SectionHeader";
import { ErrorNote } from "../components/ErrorNote";
import { getPersonalizedPrompts } from "../utils/personalizedPrompts";
import type { EmployeeSummary } from "../api/types";

export function ManagerBriefings() {
  const [selectedPerson, setSelectedPerson] = useState<string | null>(null);

  const employees = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<EmployeeSummary[]>("/employees"),
  });

  const list = employees.data ?? [];
  const activeEmployee = list.find((e) => e.name === selectedPerson) ?? list[0];
  const personalized = activeEmployee ? getPersonalizedPrompts(activeEmployee) : null;

  return (
    <div className="manager-briefings-page" aria-labelledby="briefings-title">
      <SectionHeader
        eyebrow="SUPPORTIVE BRIEFINGS"
        title="Mental wellbeing & 1-on-1 check-in guides."
        intro="Prompts for supportive dialogue between managers and team members. This system is designed to support sustainable workload and mental health — never for performance evaluation, ranking, or hike decisions."
      />

      <div className="callout callout--wellbeing" role="note" style={{ borderLeft: "4px solid var(--healthy)", background: "var(--surface)", padding: "1rem" }}>
        <p style={{ margin: 0, fontSize: "13.5px", color: "var(--ink)" }}>
          <strong>Manager Stance:</strong> Use these prompts to ask open questions (e.g. <em>&ldquo;How is your workload pacing lately?&rdquo;</em> or <em>&ldquo;Is there anything we can clear from your plate this week?&rdquo;</em>).
        </p>
      </div>

      {employees.error && <ErrorNote error={employees.error} />}

      {employees.isLoading && <p role="status">Loading team briefings…</p>}

      {!employees.isLoading && list.length === 0 && (
        <div className="welcome-state" style={{ marginTop: "1.5rem" }}>
          <h2>No team telemetry on record</h2>
          <p>Once wellbeing telemetry is processed by your wellbeing analyst, supportive 1-on-1 guides will appear here.</p>
        </div>
      )}

      {!employees.isLoading && list.length > 0 && activeEmployee && personalized && (
        <div className="briefings-layout" style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: "1.5rem", marginTop: "1.5rem" }}>
          {/* Left Column: Team Member Selector */}
          <aside className="briefings-roster" aria-label="Team Members" style={{ background: "var(--surface)", border: "1px solid var(--rule)", padding: "1rem" }}>
            <h2 style={{ margin: "0 0 10px", fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)" }}>
              Team Members
            </h2>
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "4px" }}>
              {list.map((emp) => {
                const isSelected = activeEmployee?.name === emp.name;
                return (
                  <li key={emp.name}>
                    <button
                      type="button"
                      onClick={() => setSelectedPerson(emp.name)}
                      style={{
                        width: "100%",
                        textAlign: "left",
                        padding: "8px 10px",
                        border: "1px solid",
                        borderColor: isSelected ? "var(--accent)" : "transparent",
                        background: isSelected ? "var(--accent-bg)" : "transparent",
                        color: "var(--ink)",
                        fontWeight: isSelected ? 600 : 400,
                        cursor: "pointer",
                        fontSize: "13.5px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <span>{emp.name}</span>
                      <span style={{ fontSize: "11.5px", color: "var(--muted)" }}>Week {emp.latest_week}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>

          {/* Right Column: Supportive 1-on-1 Guidance Card */}
          <main className="briefing-card" style={{ background: "var(--surface)", border: "1px solid var(--rule)", padding: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--rule)", paddingBottom: "1rem", marginBottom: "1.25rem" }}>
              <div>
                <h2 style={{ margin: 0, fontFamily: "var(--font-heading)", fontSize: "20px", color: "var(--ink)" }}>
                  1-on-1 Check-in Guide: {activeEmployee.name}
                </h2>
                <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--muted)" }}>
                  Personalized to {activeEmployee.name}&rsquo;s recent trajectory and baseline deviations.
                </p>
              </div>
              <Link to={`/person/${encodeURIComponent(activeEmployee.name)}`} className="btn btn--secondary" style={{ fontSize: "12px", padding: "4px 8px" }}>
                View full profile &rarr;
              </Link>
            </div>

            {/* Wellbeing Observation */}
            <section style={{ marginBottom: "1.5rem" }}>
              <h3 style={{ fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)", margin: "0 0 6px" }}>
                Tailored Behavioral Context
              </h3>
              <div style={{ background: "var(--paper)", borderLeft: "3px solid var(--accent)", padding: "12px 14px", fontSize: "14px", lineHeight: "1.6", color: "var(--ink)" }}>
                {personalized.contextSummary}
              </div>
            </section>

            {/* Recommended 1-on-1 Conversation Starters */}
            <section style={{ marginBottom: "1.5rem" }}>
              <h3 style={{ fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--healthy)", margin: "0 0 8px" }}>
                Suggested Conversation Starters
              </h3>
              <p style={{ margin: "0 0 10px", fontSize: "12.5px", color: "var(--muted)" }}>
                Personalized conversation prompts tailored to {activeEmployee.name}&rsquo;s specific rhythm:
              </p>
              <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "flex", flexDirection: "column", gap: "10px", fontSize: "13.5px", lineHeight: "1.6", color: "var(--ink)" }}>
                {personalized.conversationStarters.map((starter, idx) => (
                  <li key={idx}>
                    <em>{starter}</em>
                  </li>
                ))}
              </ul>
            </section>

            {/* Things to Avoid */}
            <section style={{ marginBottom: "1.5rem" }}>
              <h3 style={{ fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--exit)", margin: "0 0 8px", display: "flex", alignItems: "center", gap: "6px" }}>
                <span>⚠️</span> Demotivating Traps to Avoid with {activeEmployee.name}
              </h3>
              <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "flex", flexDirection: "column", gap: "6px", fontSize: "13px", color: "var(--ink)" }}>
                {personalized.thingsToAvoid.map((avoid, idx) => (
                  <li key={idx}>{avoid}</li>
                ))}
              </ul>
            </section>

            {/* Recommended Actions */}
            <section>
              <h3 style={{ fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)", margin: "0 0 8px" }}>
                Constructive Wellbeing Interventions
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "10px" }}>
                {personalized.recommendedSupportSteps.map((step, idx) => (
                  <div key={idx} style={{ padding: "10px 12px", background: "var(--paper)", border: "1px solid var(--rule)" }}>
                    <strong style={{ fontSize: "13px", display: "block", marginBottom: "4px", color: "var(--accent)" }}>
                      {step.icon} {step.title}
                    </strong>
                    <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)", lineHeight: "1.5" }}>
                      {step.desc}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          </main>
        </div>
      )}
    </div>
  );
}
