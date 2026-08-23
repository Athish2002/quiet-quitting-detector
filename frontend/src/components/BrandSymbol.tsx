// frontend/src/components/BrandSymbol.tsx
//
// The signature emblem for the Quiet-Quitting Detector:
// "The Equilibrium Orbit & Telemetry Waveform"
//
// Architecture:
// 1. Gyroscopic Calibration Orbit (Dual-speed rotation)
// 2. Harmonic Telemetry Sine Wave (Dynamic pulsing gradient)
// 3. Central Balance Meridian & Nucleus (Equilibrium indicator)
// 4. Tri-Node Orbital Telemetry Satellites (Output, Responsiveness, Wellbeing)

export interface BrandSymbolProps {
  size?: "sm" | "md" | "lg" | "xl" | number;
  className?: string;
  animate?: boolean;
  interactive?: boolean;
  label?: string;
}

export function BrandSymbol({
  size = "md",
  className = "",
  animate = true,
  interactive = true,
  label = "Quiet-Quitting Detector Symbol",
}: BrandSymbolProps) {
  const pixelSize =
    typeof size === "number"
      ? size
      : size === "sm"
      ? 24
      : size === "md"
      ? 34
      : size === "lg"
      ? 48
      : 64;

  return (
    <div
      className={`brand-symbol-wrapper ${interactive ? "brand-symbol--interactive" : ""} ${className}`}
      style={{
        width: `${pixelSize}px`,
        height: `${pixelSize}px`,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        position: "relative",
      }}
      aria-label={label}
      role="img"
    >
      <svg
        viewBox="0 0 100 100"
        width="100%"
        height="100%"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`brand-symbol-svg ${animate ? "brand-symbol--animated" : ""}`}
      >
        <defs>
          {/* Theme-Adaptive Primary Gradient */}
          <linearGradient id="qqd-accent-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="1" />
            <stop offset="100%" stopColor="var(--ink)" stopOpacity="0.8" />
          </linearGradient>

          {/* Glowing Waveform Gradient */}
          <linearGradient id="qqd-wave-grad" x1="0%" y1="50%" x2="100%" y2="50%">
            <stop offset="0%" stopColor="var(--muted)" stopOpacity="0.3" />
            <stop offset="30%" stopColor="var(--accent)" stopOpacity="0.9" />
            <stop offset="50%" stopColor="var(--accent)" stopOpacity="1" />
            <stop offset="70%" stopColor="var(--accent)" stopOpacity="0.9" />
            <stop offset="100%" stopColor="var(--muted)" stopOpacity="0.3" />
          </linearGradient>

          {/* Core Radial Flare */}
          <radialGradient id="qqd-core-flare" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.5" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Ambient Core Glow */}
        <circle
          cx="50"
          cy="50"
          r="28"
          fill="url(#qqd-core-flare)"
          className="brand-symbol__glow"
        />

        {/* Outer Calibrated Orbit Track (Clockwise Gyroscope) */}
        <circle
          cx="50"
          cy="50"
          r="44"
          stroke="var(--rule)"
          strokeWidth="1.5"
          strokeDasharray="4 4"
          className="brand-symbol__orbit-outer"
        />

        {/* Inner Gyroscopic Ring (Counter-Clockwise) */}
        <circle
          cx="50"
          cy="50"
          r="34"
          stroke="var(--accent)"
          strokeWidth="2"
          strokeDasharray="18 10 32 10"
          strokeLinecap="round"
          className="brand-symbol__orbit-inner"
        />

        {/* Dynamic Harmonic Waveform Spine */}
        <path
          d="M 8 50 Q 24 24, 38 50 T 68 50 T 92 50"
          stroke="url(#qqd-wave-grad)"
          strokeWidth="2.75"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="brand-symbol__wave"
        />

        {/* Horizontal Equilibrium Baseline Axis */}
        <line
          x1="12"
          y1="50"
          x2="88"
          y2="50"
          stroke="var(--rule)"
          strokeWidth="1"
          strokeDasharray="2 3"
          className="brand-symbol__axis"
        />

        {/* Central Equilibrium Nucleus */}
        <g className="brand-symbol__nucleus">
          <rect
            x="44"
            y="44"
            width="12"
            height="12"
            transform="rotate(45 50 50)"
            fill="var(--surface)"
            stroke="var(--accent)"
            strokeWidth="2"
          />
          <circle cx="50" cy="50" r="2.5" fill="var(--accent)" />
        </g>

        {/* Tri-Node Orbital Telemetry Satellites */}
        <g className="brand-symbol__satellites">
          {/* Node 1: High Output / Activity */}
          <circle cx="50" cy="6" r="3.5" fill="var(--ink)" stroke="var(--paper)" strokeWidth="1" />
          {/* Node 2: Responsiveness */}
          <circle cx="88" cy="72" r="3" fill="var(--accent)" stroke="var(--paper)" strokeWidth="1" />
          {/* Node 3: Baseline Equilibrium */}
          <circle cx="12" cy="72" r="3" fill="var(--muted)" stroke="var(--paper)" strokeWidth="1" />
        </g>
      </svg>
    </div>
  );
}
