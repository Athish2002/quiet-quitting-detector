// The app shell: fixed sidebar, a main column capped at 1160px, and the three
// global banners that sit above whichever section is open.
//
// `.app-shell` is the class that switches the Modernist token set on (see the
// block in styles.css). Everything inside it resolves --ink, --paper, --rule
// and the four classification bands from the redesign palette; anything outside
// it still sees the old values, which is what keeps the migration incremental.

import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ProviderStatus, RunProgress } from "../api/types";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  return (
    <div className="app-shell">
      {/* Skip link first in the DOM: a keyboard user should not have to tab
          through eight nav items on every section. */}
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Sidebar />
      <main className="app-main" id="main-content">
        <GlobalBanners />
        <Outlet />
      </main>
    </div>
  );
}

function GlobalBanners() {
  const [showConstraint, setShowConstraint] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setShowConstraint(false);
    }, 7000);
    return () => clearTimeout(timer);
  }, []);

  const progress = useQuery({
    queryKey: ["run-progress"],
    queryFn: () => api.get<RunProgress>("/run/progress"),
    refetchInterval: (query) => (query.state.data?.running ? 800 : false),
  });
  const providers = useQuery({
    queryKey: ["provider-status"],
    queryFn: () => api.get<ProviderStatus>("/models/status"),
  });

  const run = progress.data;
  const running = run?.running === true;
  const degraded = providers.data?.local_only_mode === true;
  const total = run?.total ?? 0;
  const done = run?.done ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;

  return (
    <>
      {running ? (
        <div className="banner banner--progress" role="status" aria-live="polite">
          <p className="banner__title">
            {run?.current ? `Evaluating ${run.current}` : "Evaluating"}
          </p>
          <div className="progress-track">
            <div className="progress-track__fill" style={{ width: `${pct}%` }} />
          </div>
          <p className="banner__count">
            {done} of {total}
          </p>
        </div>
      ) : null}

      {showConstraint ? (
        <aside className="banner banner--constraint" aria-label="Use constraint">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <p className="banner__label">Use constraint</p>
            <button
              type="button"
              className="banner__close-btn"
              onClick={() => setShowConstraint(false)}
              aria-label="Dismiss use constraint"
              style={{
                background: "transparent",
                border: "none",
                fontSize: "12px",
                cursor: "pointer",
                color: "var(--muted)",
                padding: "0 4px",
              }}
            >
              ✕
            </button>
          </div>
          <p className="banner__body">
            This system compares each person only to their own earlier weeks. It does not rank
            people, does not recommend disciplinary action, and must never be used to justify a
            decision about someone&rsquo;s employment. Every assessment you open is written to the
            access trail.
          </p>
        </aside>
      ) : null}

      {degraded ? (
        <div className="banner banner--degraded" role="status">
          <p className="banner__body">
            <strong>Degraded tier.</strong> The provider chain is unavailable, so scores come from
            the local fallback scorer. Confidence is capped at &ldquo;Not sure yet&rdquo; and no
            single number is shown for anyone.
          </p>
        </div>
      ) : null}
    </>
  );
}
