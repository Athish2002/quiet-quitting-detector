// The fixed 244px sidebar: brand, the eight sections, and a footer block
// carrying the pipeline control, model status and the theme toggle.
//
// Two deliberate departures from the design handoff, both recorded in
// design/REDESIGN_PLAN.md:
//
// R1 -- the prototype's provider-call meter ("128 / 500", "Quota resets Monday")
// is gone. This system runs on several free models with a local fallback and
// imposes no hard limit, so a quota bar would draw a constraint that does not
// exist. What replaced it is the thing an operator actually needs when output
// looks off: which model answered, and what is left in the chain behind it.
//
// The prototype's "Demo state" toggle is also gone. Empty and degraded are what
// the API returns, not states a person switches into.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api/client";
import type { ProviderStatus, RunProgress } from "../api/types";
import { ThemeToggle } from "./ThemeToggle";
import { useRole, ROLE_LABELS } from "../contexts/RoleContext";
import { BrandSymbol } from "./BrandSymbol";

/** Person detail is reached from the cohort, so it sits third but has no fixed href. */
const NAV_BEFORE_PERSON = [
  { to: "/", label: "Overview", end: true, section: "overview" },
  { to: "/cohort", label: "Cohort", end: false, section: "cohort" },
] as const;

const NAV_AFTER_PERSON = [
  { to: "/diagnostic", label: "Diagnostic room", end: false, section: "diagnostic" },
  { to: "/ingest", label: "Ingest", end: false, section: "ingest" },
  { to: "/simulator", label: "Simulator", end: false, section: "simulator" },
  { to: "/history", label: "History", end: false, section: "history" },
  { to: "/audit", label: "Access trail", end: false, section: "audit" },
] as const;

function navClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "sidebar__nav-link sidebar__nav-link--active" : "sidebar__nav-link";
}

export function Sidebar() {
  const { pathname } = useLocation();
  const onPerson = pathname.startsWith("/person/");
  const queryClient = useQueryClient();
  const { role, hasAccess } = useRole();

  const isEmployee = role === "employee";
  const isManager = role === "manager";
  const isAnalyst = role === "analyst";

  // Polls only while a run is in flight. The prototype stepped through subjects
  // on a 340ms timer; this reads real progress, so the bar cannot claim to be
  // further along than the backend is.
  const progress = useQuery({
    queryKey: ["run-progress"],
    queryFn: () => api.get<RunProgress>("/run/progress"),
    enabled: isAnalyst,
    refetchInterval: (query) => (query.state.data?.running ? 800 : false),
  });

  const providers = useQuery({
    queryKey: ["provider-status"],
    queryFn: () => api.get<ProviderStatus>("/models/status"),
    enabled: isAnalyst,
  });

  const run = useMutation({
    mutationFn: () => api.post<unknown>("/run"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["run-progress"] });
      void queryClient.invalidateQueries({ queryKey: ["employees"] });
    },
  });

  const running = progress.data?.running === true;
  const degraded = providers.data?.local_only_mode === true;

  const beforeItems = isEmployee
    ? [{ to: "/", label: "My Wellbeing", end: true, section: "my-wellbeing" }]
    : isManager
    ? [
        { to: "/", label: "Supportive Briefings", end: true, section: "briefings" },
        { to: "/cohort", label: "Cohort", end: false, section: "cohort" },
      ]
    : NAV_BEFORE_PERSON.filter((item) => hasAccess(item.section));

  const showPersonDetail = !isEmployee && hasAccess("person");
  const afterItems = isEmployee
    ? []
    : NAV_AFTER_PERSON.filter((item) => hasAccess(item.section));

  return (
    <aside className="sidebar">
      <div className="sidebar__brand" style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <BrandSymbol size={32} />
        <span className="sidebar__brand-name">
          Quiet-Quitting
          <br />
          Detector
        </span>
      </div>
      <p className="sidebar__strapline">Wellbeing prompt · not a verdict</p>

      <nav aria-label="Sections" className="sidebar__nav">
        <ul>
          {beforeItems.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} end={item.end} className={navClass}>
                {item.label}
              </NavLink>
            </li>
          ))}
          {showPersonDetail && (
            <li>
              {onPerson ? (
                <NavLink to={pathname} className={navClass}>
                  Person detail
                </NavLink>
              ) : (
                // Not a link, because there is nothing to link to until someone is
                // chosen -- and the choosing happens on the cohort, deliberately,
                // so that opening an assessment is always an explicit act.
                <span
                  className="sidebar__nav-link sidebar__nav-link--inert"
                  aria-disabled="true"
                  title="Open someone from the cohort first."
                >
                  Person detail
                </span>
              )}
            </li>
          )}
          {afterItems.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} end={item.end} className={navClass}>
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="sidebar__footer">
        {!isEmployee && (
          <>
            <p className="sidebar__label">Pipeline</p>
            {/* Deliberately not the shared `.btn` class. The old pages are now
                inside `.app-shell`, and restyling `.btn` here would silently
                restyle their buttons too. The Modernist button system arrives in
                S3, with the first section that actually replaces old markup. */}
            <button
              type="button"
              className="sidebar__run"
              onClick={() => run.mutate()}
              disabled={running || run.isPending}
            >
              {running || run.isPending ? "Run in progress…" : "Run the pipeline"}
            </button>
          </>
        )}

        <ModelBlock status={providers.data} degraded={degraded} />

        {role && (
          <div className="sidebar__role-badge">
            <span>{ROLE_LABELS[role].icon}</span>
            <span>{ROLE_LABELS[role].label}</span>
          </div>
        )}

        <ThemeToggle />
      </div>
    </aside>
  );
}

/**
 * R1's replacement for the quota meter: the model currently answering, with the
 * rest of the chain behind a disclosure.
 *
 * `<details>` rather than a custom menu on purpose -- it is keyboard operable
 * and screen-reader labelled for free, and a dropdown that needs neither state
 * nor a click-outside handler is a dropdown that cannot get stuck open.
 */
function ModelBlock({ status, degraded }: { status?: ProviderStatus; degraded: boolean }) {
  const chain = status?.fallback_sequence ?? [];
  const active = status?.last_successful_model ?? null;
  const exhausted = new Map(
    (status?.exhausted_models ?? []).map((m) => [m.model, m.cooldown_remaining_seconds]),
  );

  return (
    <div className="model-block">
      <div className="model-block__status">
        <span
          className={degraded ? "status-dot status-dot--watch" : "status-dot status-dot--healthy"}
          aria-hidden="true"
        />
        <span className="model-block__status-label">
          {degraded ? "Degraded · local fallback" : "All services operational"}
        </span>
      </div>

      {chain.length === 0 ? (
        <p className="model-block__current">Local scoring only</p>
      ) : (
        <details className="model-block__details">
          <summary>
            <span className="model-block__caption">Model</span>
            <span className="model-block__current">{active ?? "Local fallback"}</span>
          </summary>
          <ul className="model-block__chain">
            {chain.map((model) => {
              const cooldown = exhausted.get(model);
              const isActive = model === active;
              return (
                <li key={model} className={isActive ? "is-active" : undefined}>
                  <span className="model-block__chain-name">{model}</span>
                  <span className="model-block__chain-state">
                    {cooldown !== undefined
                      ? `exhausted · ${Math.ceil(cooldown / 60)}m`
                      : isActive
                        ? "in use"
                        : "ready"}
                  </span>
                </li>
              );
            })}
          </ul>
        </details>
      )}
    </div>
  );
}
