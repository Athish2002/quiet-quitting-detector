// frontend/src/pages/Home.tsx
//
// Section 1: Overview (/)
//
// An ethical, per-person view of team wellbeing. The landing section establishes
// the tool's core premise before any detail is shown: telemetry is read against
// a person's own history, never against a cohort ranking.
//
// Features:
// - Full cohort summary & 4-band distribution
// - Realtime Model Status & Model Selector (Gemini 2.5 Flash, Pro, Local Engine)
// - Calibration metrics & Ethical safeguards

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import { SectionHeader } from "../components/SectionHeader";
import { WelcomeState } from "../components/WelcomeState";
import { useRole } from "../contexts/RoleContext";
import type { CalibrationView, EmployeeSummary } from "../api/types";

interface ProviderStatusResponse {
  fallback_sequence?: string[];
  last_successful_model?: string | null;
  exhausted_models?: Array<{ model: string; cooldown_remaining_seconds: number }>;
  local_only_mode?: boolean;
}

export function Home() {
  const { role } = useRole();
  const queryClient = useQueryClient();
  const [selectedModel, setSelectedModel] = useState<string>("gemini-2.5-flash");

  const employees = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<EmployeeSummary[]>("/employees"),
  });
  const calibration = useQuery({
    queryKey: ["calibration"],
    queryFn: () => api.get<CalibrationView>("/calibration"),
  });
  const modelStatus = useQuery<ProviderStatusResponse>({
    queryKey: ["model-status"],
    queryFn: () => api.get<ProviderStatusResponse>("/models/status"),
    refetchInterval: 4000,
  });

  const updateSettingsMutation = useMutation({
    mutationFn: (params: {
      model_mode?: "auto" | "manual";
      selected_model?: string;
      local_only_mode?: boolean;
    }) => api.post("/settings", params),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["model-status"] });
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => api.post("/reset"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["employees"] });
      void queryClient.invalidateQueries({ queryKey: ["calibration"] });
      void queryClient.invalidateQueries({ queryKey: ["history"] });
    },
  });

  const error = employees.error ?? calibration.error;
  const data = employees.data ?? [];
  const cal = calibration.data?.overall;

  // Counts for the 4 bands (counts ONLY, never names, never sorted by score)
  const healthyCount = data.filter((e) => e.classification === "Healthy").length;
  const watchCount = data.filter((e) => e.classification === "Watch").length;
  const atRiskCount = data.filter((e) => e.classification === "At Risk").length;
  const exitCount = data.filter((e) => e.classification === "Silent Exit").length;
  const elevatedCount = watchCount + atRiskCount + exitCount;

  // Latest run statistics
  const latestWeek = data.length > 0 ? Math.max(...data.map((e) => e.latest_week)) : null;
  const evaluatedCount = data.length;
  const gapCount = data.filter(
    (e) => e.degraded || e.confidence === "low" || e.confidence === "none",
  ).length;

  const totalPeople = employees.data !== undefined ? data.length : null;
  const totalVerdicts = cal ? cal.total : null;
  const harmfulVerdicts = cal ? cal.harmful : null;

  const modelMode = ((modelStatus.data as unknown as Record<string, unknown>)?.model_mode as string) ?? "auto";
  const activeSelectedModel =
    ((modelStatus.data as unknown as Record<string, unknown>)?.selected_model as string) ?? selectedModel;
  const isLocalMode = modelStatus.data?.local_only_mode ?? false;
  const exhaustedList = modelStatus.data?.exhausted_models ?? [];
  const activeModelName = modelStatus.data?.last_successful_model ?? activeSelectedModel;

  return (
    <div className="overview-page">
      {error ? <ErrorNote error={error} /> : null}

      {/* 1. Hero & R2 (SectionHeader left, Band distribution + Latest run right) */}
      <div className="overview-hero">
        <SectionHeader
          eyebrow="OVERVIEW"
          title="Weekly telemetry, read against a person's own history."
          intro="An ethical, per-person view of team wellbeing. The system flags sustained divergence from an employee's own baseline and drafts supportive manager briefings — it never ranks people or compares one person to another."
          wide={true}
        />

        <aside className="overview-side" aria-label="Current status and evaluation summary">
          {/* R2 (a): Band distribution block */}
          <div className="overview-side__card" aria-labelledby="band-dist-heading">
            <p id="band-dist-heading" className="overview-side__title">
              Current distribution
            </p>
            <ul className="distribution-list" aria-label="People per classification band">
              <li className="distribution-item">
                <span className="chip chip--healthy">Healthy</span>
                <span className="distribution-count">{employees.isLoading ? "—" : healthyCount}</span>
              </li>
              <li className="distribution-item">
                <span className="chip chip--watch">Watch</span>
                <span className="distribution-count">{employees.isLoading ? "—" : watchCount}</span>
              </li>
              <li className="distribution-item">
                <span className="chip chip--at-risk">At Risk</span>
                <span className="distribution-count">{employees.isLoading ? "—" : atRiskCount}</span>
              </li>
              <li className="distribution-item">
                <span className="chip chip--exit">Silent Exit</span>
                <span className="distribution-count">{employees.isLoading ? "—" : exitCount}</span>
              </li>
            </ul>
          </div>

          {/* R2 (b): Latest run panel */}
          <div className="overview-side__card" aria-labelledby="latest-run-heading">
            <p id="latest-run-heading" className="overview-side__title">
              Latest evaluation
            </p>
            <div className="latest-run-metrics">
              <div className="latest-run-metric">
                <span>Evaluated</span>
                <strong>{employees.isLoading ? "—" : `${evaluatedCount} people`}</strong>
              </div>
              <div className="latest-run-metric">
                <span>Latest telemetry</span>
                <strong>
                  {employees.isLoading
                    ? "—"
                    : latestWeek !== null
                      ? `Week ${latestWeek}`
                      : "None"}
                </strong>
              </div>
              <div className="latest-run-metric">
                <span>Data gaps</span>
                <strong>{employees.isLoading ? "—" : `${gapCount} with gaps`}</strong>
              </div>
            </div>
            <p className="latest-run-note">Active model: see sidebar</p>
          </div>
        </aside>
      </div>

      {/* Quick Workflow Navigation Suite */}
      <nav aria-label="Quick application workflows" style={{ margin: "1.5rem 0" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "12px" }}>
          {[
            {
              to: "/cohort",
              title: "👥 Team Roster",
              desc: "Alphabetical member telemetry with quarterly filters & deviation metrics.",
            },
            {
              to: "/simulator",
              title: "🧪 Metric Simulator",
              desc: "Test behavioral archetypes in scratch mode with 0ms latency.",
            },
            {
              to: "/history",
              title: "📈 Trajectory Matrix",
              desc: "Longitudinal 52-week view across individual trends.",
            },
            {
              to: "/ingest",
              title: "📥 Data Ingestion",
              desc: "Upload telemetry via CSV, DB connection, or webhooks.",
            },
          ].map((item) => (
            <Link
              key={item.to}
              to={item.to}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "6px",
                padding: "16px 18px",
                background: "var(--surface)",
                border: "1px solid var(--rule)",
                borderRadius: "4px",
                textDecoration: "none",
                color: "var(--ink)",
                boxShadow: "0 1px 3px rgba(0, 0, 0, 0.04)",
                transition: "all 0.15s ease",
              }}
            >
              <strong style={{ fontSize: "14px", color: "var(--ink)", fontWeight: 700 }}>
                {item.title} &rarr;
              </strong>
              <span style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.45 }}>
                {item.desc}
              </span>
            </Link>
          ))}
        </div>
      </nav>

      {/* Model & Engine Control Pill: 2 Options (Choose Model vs Let Server Decide) */}
      <section
        style={{
          margin: "1.25rem 0",
          padding: "16px",
          background: "var(--surface)",
          border: "1px solid var(--rule)",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "16px" }}>
              {isLocalMode ? "🔵" : exhaustedList.length > 0 ? "🟡" : "🟢"}
            </span>
            <div>
              <strong style={{ fontSize: "13.5px", color: "var(--ink)", display: "block" }}>
                {modelMode === "auto"
                  ? "Automatic Dynamic Routing (Server Decides)"
                  : isLocalMode
                    ? "Deterministic Heuristic Engine (Local Offline Mode)"
                    : `Manual Override: Pinned to ${activeModelName === "gemini-2.5-pro" ? "Gemini 2.5 Pro" : activeModelName === "local-deterministic" ? "Deterministic Local" : "Gemini 2.5 Flash"}`}
              </strong>
              <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                {modelMode === "auto"
                  ? "Server automatically balances latency, quota, and automatic fallback chains."
                  : isLocalMode
                    ? "Zero external API calls. Running rule-based baseline scoring."
                    : "Explicit model selection active. Fallbacks trigger only on complete exhaustion."}
              </span>
            </div>
          </div>

          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <button
              type="button"
              onClick={() => resetMutation.mutate()}
              disabled={resetMutation.isPending}
              style={{
                padding: "5px 12px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
                border: "1px solid var(--rule)",
                background: "var(--paper)",
                color: "var(--muted)",
              }}
            >
              {resetMutation.isPending ? "Resetting..." : "🧹 Reset to Fresh Start"}
            </button>
          </div>
        </div>

        {/* 2 Options: Choose Model or Let Server Decide */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
            paddingTop: "10px",
            borderTop: "1px solid var(--rule)",
            flexWrap: "wrap",
          }}
        >
          <span style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--muted)" }}>
            Engine Strategy:
          </span>

          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={() => {
                updateSettingsMutation.mutate({ model_mode: "auto", local_only_mode: false });
              }}
              style={{
                padding: "5px 14px",
                fontSize: "12.5px",
                fontWeight: modelMode === "auto" ? 700 : 500,
                border: "1px solid",
                borderColor: modelMode === "auto" ? "var(--accent)" : "var(--rule)",
                background: modelMode === "auto" ? "var(--accent-bg)" : "var(--paper)",
                color: modelMode === "auto" ? "var(--ink)" : "var(--muted)",
                cursor: "pointer",
              }}
            >
              🤖 Let the server decide
            </button>

            <button
              type="button"
              onClick={() => {
                updateSettingsMutation.mutate({ model_mode: "manual", selected_model: activeSelectedModel });
              }}
              style={{
                padding: "5px 14px",
                fontSize: "12.5px",
                fontWeight: modelMode === "manual" ? 700 : 500,
                border: "1px solid",
                borderColor: modelMode === "manual" ? "var(--accent)" : "var(--rule)",
                background: modelMode === "manual" ? "var(--accent-bg)" : "var(--paper)",
                color: modelMode === "manual" ? "var(--ink)" : "var(--muted)",
                cursor: "pointer",
              }}
            >
              🎛️ Choose model
            </button>
          </div>

          {/* If manual mode is selected, reveal the model options */}
          {modelMode === "manual" && (
            <div style={{ display: "flex", gap: "6px", alignItems: "center", marginLeft: "auto", flexWrap: "wrap" }}>
              <span style={{ fontSize: "11.5px", color: "var(--muted)", marginRight: "4px" }}>
                Select Tier:
              </span>
              {[
                { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
                { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
                { id: "local-deterministic", label: "Deterministic Local (Offline)" },
              ].map((m) => {
                const isSelected = isLocalMode
                  ? m.id === "local-deterministic"
                  : activeSelectedModel === m.id && m.id !== "local-deterministic";
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => {
                      setSelectedModel(m.id);
                      updateSettingsMutation.mutate({
                        model_mode: "manual",
                        selected_model: m.id,
                        local_only_mode: m.id === "local-deterministic",
                      });
                    }}
                    style={{
                      padding: "4px 10px",
                      fontSize: "12px",
                      fontWeight: isSelected ? 700 : 500,
                      border: "1px solid",
                      borderColor: isSelected ? "var(--accent)" : "var(--rule)",
                      background: isSelected ? "var(--accent-bg)" : "var(--paper)",
                      color: isSelected ? "var(--ink)" : "var(--muted)",
                      cursor: "pointer",
                    }}
                  >
                    {m.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {/* 3. Stat strip: 4 equal columns with rules between & under */}
      <section aria-label="Summary statistics" className="stat-strip">
        <div className="stat-cell">
          <p className="stat-cell__label">People on record</p>
          <p className="stat-cell__numeral">
            {employees.isLoading ? "—" : totalPeople ?? 0}
          </p>
          <p className="stat-cell__note">Active in current cohort</p>
        </div>
        <div className="stat-cell">
          <p className="stat-cell__label">Currently raised above Healthy</p>
          <p className="stat-cell__numeral">
            {employees.isLoading ? "—" : elevatedCount}
          </p>
          <p className="stat-cell__note">Watch, At Risk, or Silent Exit</p>
        </div>
        <div className="stat-cell">
          <p className="stat-cell__label">Manager verdicts recorded</p>
          <p className="stat-cell__numeral">
            {calibration.isLoading ? "—" : totalVerdicts ?? 0}
          </p>
          <p className="stat-cell__note">Feedback on model accuracy</p>
        </div>
        <div className="stat-cell">
          <p className="stat-cell__label">Reported as harmful</p>
          <p className="stat-cell__numeral">
            {calibration.isLoading ? "—" : harmfulVerdicts ?? 0}
          </p>
          <p className="stat-cell__note">Verdicts flagged harmful</p>
        </div>
      </section>

      {/* 6. Empty state notice / calibration caveat */}
      {calibration.data && !calibration.data.overall.total ? (
        <div className="overview-notice" role="status">
          <p>
            <strong>No manager verdicts recorded.</strong> No manager has told this system
            whether it was right yet, so nothing it reports has been validated. Treat every
            assessment as a question.
          </p>
        </div>
      ) : null}

      {!employees.isLoading && employees.data !== undefined && employees.data.length === 0 ? (
        <WelcomeState role={role ?? "analyst"} />
      ) : null}

      {calibration.data?.review_required ? (
        <div className="overview-notice overview-notice--alert" role="alert">
          <p>
            <strong>Calibration review required.</strong> Calibration is outside the acceptable
            range.{" "}
            <Link to="/diagnostic">Review it before relying on any assessment.</Link>
          </p>
        </div>
      ) : null}

      {/* 4. What this is, and what it is not */}
      <section
        aria-labelledby="stance-heading"
        className="stance-section"
        style={{
          margin: "2.5rem 0",
          padding: "1.75rem 2rem",
          background: "var(--surface)",
          border: "1px solid var(--rule)",
          borderRadius: "4px",
          boxShadow: "0 1px 3px rgba(0, 0, 0, 0.03)",
        }}
      >
        <h2 id="stance-heading" className="sr-only">
          Ethical Safeguards &amp; Governance
        </h2>
        <div className="stance-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "2rem", marginBottom: "1.5rem" }}>
          <div className="stance-col">
            <p className="stance-col__label" style={{ fontSize: "12px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--healthy)", marginBottom: "12px", display: "flex", alignItems: "center", gap: "6px" }}>
              <span>✓</span> IT DOES
            </p>
            <ul className="stance-list" style={{ margin: 0, paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "10px", fontSize: "13.5px", color: "var(--ink)", lineHeight: "1.5" }}>
              <li>
                Compare each person to their <strong>own</strong> earlier weeks.
              </li>
              <li>
                Require a pattern to hold for two or more consecutive weeks, and to still be
                happening now.
              </li>
              <li>Say when it is not confident, instead of showing a number.</li>
              <li>Explain which metric drove a score.</li>
            </ul>
          </div>
          <div className="stance-col">
            <p className="stance-col__label" style={{ fontSize: "12px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--at-risk)", marginBottom: "12px", display: "flex", alignItems: "center", gap: "6px" }}>
              <span>✕</span> IT DOES NOT
            </p>
            <ul className="stance-list" style={{ margin: 0, paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "10px", fontSize: "13.5px", color: "var(--ink)", lineHeight: "1.5" }}>
              <li>Rank people, or compare one person to another.</li>
              <li>Recommend disciplinary action, ever.</li>
              <li>
                Hold anything about health, sentiment, or performance ratings — there is no
                field for them.
              </li>
              <li>Treat missing data as evidence of anything.</li>
            </ul>
          </div>
        </div>
        <p className="stance-closing" style={{ margin: 0, paddingTop: "1.25rem", borderTop: "1px solid var(--rule)", fontSize: "12.5px", color: "var(--muted)", lineHeight: "1.6", fontStyle: "italic" }}>
          This is a prompt for a conversation, not a verdict about a person. If it is ever used to
          justify a decision about someone&apos;s employment, it is being used for something it was
          explicitly built not to do.
        </p>
      </section>

      {/* 5. Three Link Cards */}
      <section aria-labelledby="links-heading" className="overview-links">
        <h2 id="links-heading" className="sr-only">
          Core sections
        </h2>
        <div className="link-cards-grid">
          <Link to="/cohort" className="link-card">
            <p className="link-card__eyebrow">Section 02</p>
            <h3 className="link-card__title">Cohort</h3>
            <p className="link-card__body">
              Weekly telemetry across the full cohort. Alphabetical, unranked, with deviation bars
              against each person's own baseline.
            </p>
            <span className="link-card__action">Open cohort &rarr;</span>
          </Link>

          <Link to="/diagnostic" className="link-card">
            <p className="link-card__eyebrow">Section 04</p>
            <h3 className="link-card__title">Diagnostic room</h3>
            <p className="link-card__body">
              Model calibration, harm rates, and the closed-vocabulary manager verdict form.
            </p>
            <span className="link-card__action">Open diagnostic room &rarr;</span>
          </Link>

          <Link to="/audit" className="link-card">
            <p className="link-card__eyebrow">Section 08</p>
            <h3 className="link-card__title">Access trail</h3>
            <p className="link-card__body">
              Immutable cryptographic log of every assessment opened, who viewed it, and retention
              schedules.
            </p>
            <span className="link-card__action">Open access trail &rarr;</span>
          </Link>
        </div>
      </section>
    </div>
  );
}
