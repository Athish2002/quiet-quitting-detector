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

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import { SectionHeader } from "../components/SectionHeader";
import type { Attribution, EmployeeSummary, RunProgress } from "../api/types";

export function Cohort() {
  const { data, isPending, error } = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<EmployeeSummary[]>("/employees"),
  });

  const { data: progress } = useQuery({
    queryKey: ["run-progress"],
    queryFn: () => api.get<RunProgress>("/run/progress"),
    refetchInterval: (query) => (query.state.data?.running ? 3000 : false),
  });

  const sorted = data ? [...data].sort((a, b) => a.name.localeCompare(b.name)) : [];

  return (
    <div className="cohort-page" aria-labelledby="cohort-title">
      <SectionHeader
        eyebrow="COHORT"
        title="Full team telemetry, evaluated against each person's own baseline."
        intro="Listed alphabetically. There is no sort control and no ranking — comparing people to each other is the one thing this system was explicitly built not to do."
      />

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
        <div className="cohort-empty">
          <p className="cohort-empty__heading">Nobody on record yet.</p>
          <p className="cohort-empty__body">
            Ingest a week of telemetry to evaluate the team.
          </p>
          <Link to="/ingest" className="btn btn--primary">
            Go to Ingest &rarr;
          </Link>
        </div>
      ) : null}

      {sorted.length > 0 ? (
        <div className="cohort-grid" role="region" aria-label="Team Cohort List">
          {sorted.map((employee) => (
            <CohortCard key={employee.name} employee={employee} />
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
): MetricDeviation[] {
  const metricsConfig = [
    {
      key: "completed_tasks",
      aliases: ["tasks", "completed_tasks", "tasks_completed", "tasks completed"],
      label: "Tasks completed",
      isAdverse: (delta: number) => delta < 0,
    },
    {
      key: "response_time",
      aliases: ["response", "response_time", "avg_response_time_hours", "response time"],
      label: "Response time",
      isAdverse: (delta: number) => delta > 0,
    },
    {
      key: "weekly_hours",
      aliases: ["hours", "weekly_hours", "weekly hours"],
      label: "Weekly hours",
      isAdverse: (delta: number) => delta < 0,
    },
    {
      key: "after_hours_logins",
      aliases: ["after_hours", "after_hours_logins", "after-hours", "after-hours logins"],
      label: "After-hours logins",
      isAdverse: (_delta: number) => false, // always inert
    },
  ];

  return metricsConfig.map((config) => {
    const attr = attributions.find((a) => {
      const m = a.metric.toLowerCase();
      return config.aliases.some((alias) => m === alias || m.includes(alias));
    });

    let delta = 0;
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

function CohortCard({ employee }: { employee: EmployeeSummary }) {
  const bandClass = getBandClass(employee.classification);
  const deviations = calculateMetricDeviations(employee.attributions);

  const confLabel =
    employee.confidence === "none"
      ? "No usable evidence"
      : employee.confidence === "low"
        ? "Not sure yet"
        : employee.confidence === "moderate"
          ? "Moderate confidence"
          : employee.confidence === "high"
            ? "Well evidenced"
            : "Confidence unrecorded";

  const firstSignal = employee.signals?.[0];
  const headline =
    employee.signals && employee.signals.length > 0 && firstSignal
      ? `${employee.signals.length} confirmed pattern${
          employee.signals.length > 1 ? "s" : ""
        } · ${firstSignal.signal_name ?? firstSignal.signal ?? "signal detected"}`
      : "No confirmed patterns in this window.";

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
            Latest week {employee.latest_week}
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
