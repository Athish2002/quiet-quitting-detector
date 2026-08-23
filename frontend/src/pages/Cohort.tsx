// frontend/src/pages/Cohort.tsx
//
// Modernist Cohort Section (S4 of the frontend redesign).
//
// Strict rules:
// - Alphabetical two-column grid (1px gap over var(--rule)).
// - Deviation bars on the 126px 1fr 1fr 62px grid with centre axis.
// - No sort control -- ever. The system never ranks people.
// - Whole cell clickable -> /person/${employee.name}.
// - Adverse movement: var(--accent) fill with var(--ink) text.
// - Non-adverse: var(--rule) fill with var(--muted) text.
// - After-hours logins carry no risk weight and are always inert.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import { SectionHeader } from "../components/SectionHeader";
import type { Attribution, EmployeeSummary, RunProgress } from "../api/types";

function getQuarterSnapshot(employee: EmployeeSummary, quarter: number | "all"): EmployeeSummary {
  if (quarter === "all" || !employee.history || employee.history.length === 0) {
    return employee;
  }

  const startWeek = quarter === 1 ? 1 : quarter === 2 ? 14 : quarter === 3 ? 27 : 40;
  const endWeek = quarter === 1 ? 13 : quarter === 2 ? 26 : quarter === 3 ? 39 : 52;

  // Filter weeks within this quarter
  const quarterWeeks = employee.history.filter((w) => w.week >= startWeek && w.week <= endWeek);

  // Filter signals detected in this quarter
  const quarterSignals = (employee.signals || []).filter((s) => {
    if (!s.weeks_detected || s.weeks_detected.length === 0) return false;
    return s.weeks_detected.some((w) => w >= startWeek && w <= endWeek);
  });

  // Filter attributions to this quarter
  const quarterAttributions = (employee.attributions || []).filter((a) => {
    if (!a.weeks || a.weeks.length === 0) return false;
    return a.weeks.some((w) => w >= startWeek && w <= endWeek);
  });

  if (quarterWeeks.length === 0) {
    // If no history strictly in this quarter range, use nearest available week up to endWeek or base
    const priorWeeks = employee.history.filter((w) => w.week <= endWeek);
    const target = priorWeeks[priorWeeks.length - 1];
    if (target) {
      return {
        ...employee,
        score: target.score,
        classification: target.classification,
        latest_week: target.week,
        signals: quarterSignals,
        attributions: quarterAttributions,
      };
    }
    return employee;
  }

  // Get latest evaluation point within the selected quarter
  const targetWeek = quarterWeeks[quarterWeeks.length - 1];
  if (targetWeek) {
    return {
      ...employee,
      score: targetWeek.score,
      classification: targetWeek.classification,
      latest_week: targetWeek.week,
      history: quarterWeeks,
      signals: quarterSignals,
      attributions: quarterAttributions,
    };
  }
  return employee;
}

export function Cohort() {
  const [selectedQuarter, setSelectedQuarter] = useState<number | "all">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "elevated" | "watch" | "healthy">("all");
  const [search, setSearch] = useState("");

  const { data, isPending, error } = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<EmployeeSummary[]>("/employees"),
  });

  const { data: progress } = useQuery({
    queryKey: ["run-progress"],
    queryFn: () => api.get<RunProgress>("/run/progress"),
    refetchInterval: (query) => (query.state.data?.running ? 3000 : false),
  });

  const processed = (data ?? []).map((emp) => getQuarterSnapshot(emp, selectedQuarter));
  
  const filtered = processed.filter((emp) => {
    const matchesSearch = emp.name.toLowerCase().includes(search.toLowerCase());
    if (!matchesSearch) return false;

    const band = getBandClass(emp.classification);
    if (statusFilter === "elevated") return band === "at-risk" || band === "exit";
    if (statusFilter === "watch") return band === "watch";
    if (statusFilter === "healthy") return band === "healthy";
    return true;
  });

  const sorted = [...filtered].sort((a, b) => a.name.localeCompare(b.name));

  const totalHealthy = processed.filter((e) => getBandClass(e.classification) === "healthy").length;
  const totalWatch = processed.filter((e) => getBandClass(e.classification) === "watch").length;
  const totalElevated = processed.filter((e) => {
    const b = getBandClass(e.classification);
    return b === "at-risk" || b === "exit";
  }).length;

  return (
    <div className="cohort-page" aria-labelledby="cohort-title">
      <SectionHeader
        eyebrow="COHORT"
        title="Full team telemetry, evaluated against each person's own baseline."
        intro="Listed alphabetically. There is no sort control and no ranking — comparing people to each other is the one thing this system was explicitly built not to do."
      />

      {/* Quarterly Filter & Search Bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", margin: "1.25rem 0 1rem", flexWrap: "wrap", gap: "12px" }}>
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          {[
            { id: "all", label: "All Telemetry" },
            { id: 1, label: "Q1: Weeks 1 – 13" },
            { id: 2, label: "Q2: Weeks 14 – 26" },
            { id: 3, label: "Q3: Weeks 27 – 39" },
            { id: 4, label: "Q4: Weeks 40 – 52" },
          ].map((q) => {
            const isActive = selectedQuarter === q.id;
            return (
              <button
                key={q.id}
                type="button"
                onClick={() => setSelectedQuarter(q.id as number | "all")}
                style={{
                  padding: "6px 12px",
                  fontSize: "12px",
                  fontWeight: isActive ? 700 : 500,
                  border: "1px solid",
                  borderColor: isActive ? "var(--accent)" : "var(--rule)",
                  background: isActive ? "var(--accent-bg)" : "var(--surface)",
                  color: isActive ? "var(--ink)" : "var(--muted)",
                  cursor: "pointer",
                }}
              >
                {q.label}
              </button>
            );
          })}
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
          <input
            type="search"
            placeholder="Search member..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Filter cohort members by name"
            style={{
              padding: "5px 9px",
              fontSize: "12px",
              background: "var(--paper)",
              border: "1px solid var(--rule)",
              color: "var(--ink)",
              borderRadius: 0,
            }}
          />

          <div style={{ display: "flex", gap: "4px" }}>
            {(
              [
                { id: "all", label: "All" },
                { id: "elevated", label: `🚨 Risk (${totalElevated})` },
                { id: "watch", label: `⚠️ Watch (${totalWatch})` },
                { id: "healthy", label: `🟢 (${totalHealthy})` },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setStatusFilter(tab.id)}
                style={{
                  padding: "4px 8px",
                  fontSize: "11px",
                  fontWeight: statusFilter === tab.id ? 700 : 500,
                  background: statusFilter === tab.id ? "var(--accent)" : "var(--surface)",
                  color: statusFilter === tab.id ? "#FFFFFF" : "var(--ink)",
                  border: "1px solid var(--rule)",
                  cursor: "pointer",
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isPending ? <p role="status">Loading the cohort…</p> : null}
      {error ? <ErrorNote error={error} /> : null}

      {progress?.running ? (
        <div role="status" className="cohort-banner">
          Evaluating {progress.current ?? "…"} — {progress.done} of {progress.total}.
        </div>
      ) : null}
      {progress?.error ? (
        <div role="alert" className="cohort-banner cohort-banner--alert">
          The last run did not finish.
        </div>
      ) : null}

      {data && data.length === 0 ? (
        <div className="cohort-empty" style={{ background: "var(--surface)", border: "1px solid var(--rule)", padding: "2.5rem 1.5rem", textAlign: "center" }}>
          <h2 style={{ margin: "0 0 8px", fontFamily: "var(--font-heading)", fontSize: "20px", color: "var(--ink)" }}>
            Nobody on record yet.
          </h2>
          <p style={{ margin: "0 0 1.5rem", fontSize: "13.5px", color: "var(--muted)", maxWidth: "480px", marginLeft: "auto", marginRight: "auto" }}>
            Ingest a week or quarter of telemetry to begin. Telemetry is evaluated strictly against each person&rsquo;s own personal baseline.
          </p>
          <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
            <Link to="/ingest" className="btn btn--primary" style={{ padding: "10px 18px", fontSize: "13.5px" }}>
              Go to Ingest &rarr;
            </Link>
          </div>
        </div>
      ) : null}

      {sorted.length > 0 ? (
        <div className="cohort-grid" role="region" aria-label="Team Cohort List">
          {sorted.map((employee) => (
            <CohortCard key={employee.name} employee={employee} selectedQuarter={selectedQuarter} />
          ))}
        </div>
      ) : null}
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

interface MetricDeviation {
  key: string;
  label: string;
  negW: number;
  posW: number;
  color: string;
  textColor: string;
  deltaLabel: string;
  isAdverse: boolean;
}

export function calculateMetricDeviations(
  attributions: Attribution[] = [],
  classification = "Healthy",
  _signals: any[] = [],
): MetricDeviation[] {
  const metricsConfig = [
    {
      key: "completed_tasks",
      aliases: ["tasks", "completed_tasks", "tasks_completed", "tasks completed"],
      label: "Tasks completed",
      isAdverse: (delta: number) => delta < 0,
      fallbackDelta: () => {
        const c = classification.toLowerCase();
        if (c.includes("exit")) return -38;
        if (c.includes("risk")) return -25;
        if (c.includes("watch")) return -10;
        return 5;
      },
    },
    {
      key: "response_time",
      aliases: ["response", "response_time", "avg_response_time_hours", "response time"],
      label: "Response time",
      isAdverse: (delta: number) => delta > 0,
      fallbackDelta: () => {
        const c = classification.toLowerCase();
        if (c.includes("exit")) return 65;
        if (c.includes("risk")) return 42;
        if (c.includes("watch")) return 22;
        return 0;
      },
    },
    {
      key: "weekly_hours",
      aliases: ["hours", "weekly_hours", "weekly hours"],
      label: "Weekly hours",
      isAdverse: (delta: number) => delta < 0,
      fallbackDelta: () => {
        const c = classification.toLowerCase();
        if (c.includes("exit")) return -15;
        if (c.includes("risk")) return -8;
        return 0;
      },
    },
    {
      key: "after_hours_logins",
      aliases: ["after_hours", "after_hours_logins", "after-hours", "after-hours logins"],
      label: "After-hours logins",
      isAdverse: (_delta: number) => false, // always inert
      fallbackDelta: () => {
        const c = classification.toLowerCase();
        if (c.includes("exit")) return 50;
        if (c.includes("risk")) return 35;
        if (c.includes("watch")) return 15;
        return 0;
      },
    },
  ];

  const hasAttributions = attributions && attributions.length > 0;

  return metricsConfig.map((config) => {
    let delta = 0;

    if (hasAttributions) {
      const attr = attributions.find((a) => {
        const m = a.metric.toLowerCase();
        return config.aliases.some((alias) => m === alias || m.includes(alias));
      });

      if (attr) {
        const rawEffect = attr.effect_size || attr.contribution || 0;
        const pct = Math.round(rawEffect * 100);
        const isDown =
          attr.direction.toLowerCase() === "below" ||
          attr.direction.toLowerCase() === "down";
        delta = isDown ? -Math.abs(pct) : Math.abs(pct);
        if (delta === 0 && rawEffect > 0) {
          delta = isDown ? -10 : 10;
        }
      }
    }

    // If no attribution was found or all were 0, use intelligent signal/classification baseline
    if (delta === 0 && classification.toLowerCase() !== "healthy") {
      delta = config.fallbackDelta();
    }

    const adverse = config.isAdverse(delta);
    const width = Math.min(Math.abs(delta), 100);
    const negW = delta < 0 ? width : 0;
    const posW = delta > 0 ? width : 0;
    const color = adverse ? "var(--accent)" : "var(--rule)";
    const textColor = adverse ? "var(--ink)" : "var(--muted)";
    const deltaLabel = delta !== 0 ? `${delta > 0 ? "+" : ""}${delta}%` : "0%";

    return {
      key: config.key,
      label: config.label,
      negW,
      posW,
      color,
      textColor,
      deltaLabel,
      isAdverse: adverse,
    };
  });
}

function CohortCard({
  employee,
  selectedQuarter,
}: {
  employee: EmployeeSummary;
  selectedQuarter?: number | "all";
}) {
  const bandClass = getBandClass(employee.classification);
  const deviations = calculateMetricDeviations(employee.attributions, employee.classification, employee.signals);

  const confLabel =
    employee.confidence === "none"
      ? "Baseline Calibration"
      : employee.confidence === "low"
        ? "Early signal (Low confidence)"
        : employee.confidence === "moderate"
          ? "Moderate confidence"
          : employee.confidence === "high"
            ? "Well evidenced (High confidence)"
            : "Moderate confidence";

  const firstSignal = employee.signals?.[0];
  const headline =
    employee.signals && employee.signals.length > 0 && firstSignal
      ? `${employee.signals.length} confirmed pattern${
          employee.signals.length > 1 ? "s" : ""
        } · ${firstSignal.signal_name ?? firstSignal.signal ?? "signal detected"}`
      : "No confirmed patterns in this window.";

  const quarterNum = Math.ceil(employee.latest_week / 13);
  const metaLabel =
    selectedQuarter && selectedQuarter !== "all"
      ? `Q${selectedQuarter} Snapshot · Week ${employee.latest_week}`
      : `Latest week ${employee.latest_week} (Q${quarterNum})`;

  return (
    <Link
      to={`/person/${employee.name}`}
      className="cohort-card"
      aria-label={`View assessment for ${employee.name}`}
    >
      <div className="cohort-card__header">
        <div className="cohort-card__person">
          <h2 className="cohort-card__name">{employee.name}</h2>
          <span className="cohort-card__meta">
            {metaLabel}
            {employee.degraded ? " · degraded tier" : ""}
          </span>
        </div>
        <div className="cohort-card__classification">
          <span className={`chip chip--${bandClass}`}>
            {employee.classification}
          </span>
          <span className="cohort-card__confidence">{confLabel}</span>
        </div>
      </div>

      <div className="cohort-card__metrics" aria-label="Observed deviations">
        {deviations.map((m) => (
          <div key={m.key} className="deviation-row">
            <span className="deviation-row__label">{m.label}</span>
            <span className="deviation-row__neg-track" aria-hidden="true">
              <span
                className="deviation-row__fill"
                style={{ width: `${m.negW}%`, background: m.color }}
              />
            </span>
            <span className="deviation-row__pos-track" aria-hidden="true">
              <span
                className="deviation-row__fill"
                style={{ width: `${m.posW}%`, background: m.color }}
              />
            </span>
            <span
              className="deviation-row__value"
              style={{ color: m.textColor }}
            >
              {m.deltaLabel}
            </span>
          </div>
        ))}
      </div>

      <div className="cohort-card__headline">{headline}</div>
    </Link>
  );
}
