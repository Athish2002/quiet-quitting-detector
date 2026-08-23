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
  const [copied, setCopied] = useState(false);

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
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--rule)", paddingBottom: "1rem", marginBottom: "1.25rem", flexWrap: "wrap", gap: "10px" }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                  <h2 style={{ margin: 0, fontFamily: "var(--font-heading)", fontSize: "20px", color: "var(--ink)" }}>
                    1-on-1 Check-in Guide: {activeEmployee.name}
                  </h2>
                  <span style={{ fontSize: "11px", padding: "2px 8px", background: "var(--healthy-bg)", color: "var(--healthy)", border: "1px solid var(--healthy)", fontWeight: 600 }}>
                    Psychological Safety Guardrails Active
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: "13px", color: "var(--muted)" }}>
                  COACH Framework · Personalized to {activeEmployee.name}&rsquo;s baseline trajectory.
                </p>
              </div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <button
                  type="button"
                  onClick={() => {
                    const text = [
                      `# 1-on-1 Supportive Wellbeing Check-In: ${activeEmployee.name}`,
                      `Framework: COACH (Connect • Observe • Ask • Collaborate • Help)`,
                      `Evaluation Mode: Non-punitive personal baseline assessment\n`,
                      `## 🔍 Context Summary`,
                      `${personalized.contextSummary}\n`,
                      `## 💬 Suggested Empathetic Starters`,
                      ...personalized.conversationStarters.map((s) => `- ${s}`),
                      `\n## ⚠️ Anti-Patterns to Avoid`,
                      ...personalized.thingsToAvoid.map((a) => `- [AVOID] ${a}`),
                      `\n## 🤝 Actionable Support Steps`,
                      ...personalized.recommendedSupportSteps.map((st) => `- ${st.title}: ${st.desc}`),
                    ].join("\n");

                    void navigator.clipboard.writeText(text);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 2500);
                  }}
                  className="btn btn--secondary"
                  style={{
                    fontSize: "12px",
                    padding: "6px 12px",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    cursor: "pointer",
                    background: copied ? "var(--healthy-bg)" : "var(--paper)",
                    borderColor: copied ? "var(--healthy)" : "var(--rule)",
                    color: copied ? "var(--healthy)" : "var(--ink)",
                    fontWeight: 600,
                  }}
                  title="Copy formatted 1-on-1 meeting guide for your agenda"
                >
                  <span>{copied ? "✓ Copied Guide!" : "📋 Copy Meeting Plan"}</span>
                </button>
                <Link to={`/person/${encodeURIComponent(activeEmployee.name)}`} className="btn btn--secondary" style={{ fontSize: "12px", padding: "6px 10px" }}>
                  Full Profile &rarr;
                </Link>
              </div>
            </div>

            {/* COACH Workflow Bar */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "6px", marginBottom: "1.5rem", textAlign: "center", fontSize: "11px" }}>
              <div style={{ padding: "6px", background: "var(--paper)", border: "1px solid var(--rule)" }}>
                <strong style={{ display: "block", color: "var(--accent)" }}>1. Connect</strong>
                <span style={{ color: "var(--muted)" }}>Check-in first</span>
              </div>
              <div style={{ padding: "6px", background: "var(--paper)", border: "1px solid var(--rule)" }}>
                <strong style={{ display: "block", color: "var(--accent)" }}>2. Observe</strong>
                <span style={{ color: "var(--muted)" }}>Share context</span>
              </div>
              <div style={{ padding: "6px", background: "var(--paper)", border: "1px solid var(--rule)" }}>
                <strong style={{ display: "block", color: "var(--accent)" }}>3. Ask</strong>
                <span style={{ color: "var(--muted)" }}>Open dialogue</span>
              </div>
              <div style={{ padding: "6px", background: "var(--paper)", border: "1px solid var(--rule)" }}>
                <strong style={{ display: "block", color: "var(--accent)" }}>4. Collaborate</strong>
                <span style={{ color: "var(--muted)" }}>Unblock scope</span>
              </div>
              <div style={{ padding: "6px", background: "var(--paper)", border: "1px solid var(--rule)" }}>
                <strong style={{ display: "block", color: "var(--accent)" }}>5. Help</strong>
                <span style={{ color: "var(--muted)" }}>Protect rest</span>
              </div>
            </div>

            {/* Wellbeing Observation */}
            <section style={{ marginBottom: "1.5rem" }}>
              <h3 style={{ fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)", margin: "0 0 6px" }}>
                Observed Behavioral Context
              </h3>
              <div style={{ background: "var(--paper)", borderLeft: "3px solid var(--accent)", padding: "12px 14px", fontSize: "14px", lineHeight: "1.6", color: "var(--ink)" }}>
                {personalized.contextSummary}
              </div>
            </section>

            {/* DO vs DONT Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.25rem", marginBottom: "1.5rem" }}>
              {/* Recommended 1-on-1 Conversation Starters */}
              <section style={{ background: "var(--paper)", border: "1px solid var(--rule)", borderTop: "3px solid var(--healthy)", padding: "12px 14px" }}>
                <h3 style={{ fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--healthy)", margin: "0 0 8px", display: "flex", alignItems: "center", gap: "6px" }}>
                  <span>✓</span> Empathetic Conversation Starters (DO)
                </h3>
                <ul style={{ margin: 0, paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: "10px", fontSize: "13px", lineHeight: "1.55", color: "var(--ink)" }}>
                  {personalized.conversationStarters.map((starter, idx) => (
                    <li key={idx}>
                      <em>{starter}</em>
                    </li>
                  ))}
                </ul>
              </section>

              {/* Things to Avoid */}
              <section style={{ background: "var(--paper)", border: "1px solid var(--rule)", borderTop: "3px solid var(--exit)", padding: "12px 14px" }}>
                <h3 style={{ fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--exit)", margin: "0 0 8px", display: "flex", alignItems: "center", gap: "6px" }}>
                  <span>⚠️</span> Demotivating Traps (DON&rsquo;T)
                </h3>
                <ul style={{ margin: 0, paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: "8px", fontSize: "13px", lineHeight: "1.5", color: "var(--ink)" }}>
                  {personalized.thingsToAvoid.map((avoid, idx) => (
                    <li key={idx}>{avoid}</li>
                  ))}
                </ul>
              </section>
            </div>

            {/* Recommended Actions */}
            <section>
              <h3 style={{ fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)", margin: "0 0 8px" }}>
                Concrete Support & Rebalancing Actions
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
