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
            viewBox="0 0 400 20"
            className="telemetry-pulse-bar__wave-svg"
            preserveAspectRatio="none"
          >
            <path
              d="M 0 10 Q 50 2, 100 10 T 200 10 T 300 10 T 400 10"
              fill="none"
              stroke="var(--accent)"
              strokeWidth="1.5"
              className="telemetry-pulse-bar__wave-path"
            />
            <line
              x1="0"
              y1="10"
              x2="400"
              y2="10"
              stroke="var(--rule)"
              strokeWidth="1"
              strokeDasharray="3 3"
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
