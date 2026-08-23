// frontend/src/components/TelemetryPulseBar.tsx
//
// Minimalist Telemetry Pulse Bar:
// A sleek, modernist ambient status ribbon showing real-time baseline equilibrium
// with fluid waveform animation and theme-aware lighting.

import { useState } from "react";
import { BrandSymbol } from "./BrandSymbol";

export function TelemetryPulseBar() {
  const [hovered, setHovered] = useState(false);

  return (
    <aside
      className={`telemetry-pulse-bar ${hovered ? "telemetry-pulse-bar--active" : ""}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      aria-label="System telemetry equilibrium monitor"
      role="complementary"
    >
      <div className="telemetry-pulse-bar__inner">
        <div className="telemetry-pulse-bar__status">
          <span className="telemetry-pulse-bar__beacon" aria-hidden="true" />
          <span className="telemetry-pulse-bar__label">Baseline Equilibrium Active</span>
          <span className="telemetry-pulse-bar__badge">Self-Referential Metric Stream</span>
        </div>

        <div className="telemetry-pulse-bar__wave-container" aria-hidden="true">
          <svg
            viewBox="0 0 320 20"
            className="telemetry-pulse-bar__wave-svg"
            preserveAspectRatio="none"
          >
            <defs>
              <linearGradient id="qqdPulseGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.2" />
                <stop offset="50%" stopColor="var(--accent)" stopOpacity="1" />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.2" />
              </linearGradient>
            </defs>
            <line
              x1="0"
              y1="10"
              x2="320"
              y2="10"
              stroke="var(--rule)"
              strokeWidth="1"
              strokeDasharray="2 3"
            />
            <path
              d="M 0 10 Q 40 2, 80 10 T 160 10 T 240 10 T 320 10"
              fill="none"
              stroke="url(#qqdPulseGrad)"
              strokeWidth="2"
              className="telemetry-pulse-bar__wave-path"
            />
            <circle
              cx="0"
              cy="10"
              r="3.5"
              fill="var(--accent)"
              className="telemetry-pulse-bar__pulse-dot"
            />
          </svg>
        </div>

        <div className="telemetry-pulse-bar__metric">
          <BrandSymbol size={18} animate={hovered} />
          <span className="telemetry-pulse-bar__fidelity">Zero-Surveillance Mode</span>
        </div>
      </div>
    </aside>
  );
}
