

interface TrajectoryBarsProps {
  data: { label: string; value: number }[];
}

export function TrajectoryBars({ data }: TrajectoryBarsProps) {
  if (!data || data.length === 0) return null;
  return (
    <section aria-label="Trajectory" style={{ marginBottom: "1rem" }}>
      <h3 style={{ marginBottom: "0.5rem", color: "var(--ink)" }}>Trajectory</h3>
      <div style={{ display: "flex", gap: "0.5rem" }}>
        {data.map((point, idx) => (
          <div key={idx} style={{ textAlign: "center" }}>
            <div
              style={{
                background: "var(--accent-tint)",
                height: `${point.value * 1.5}px`,
                width: "12px",
                borderRadius: "var(--radius)",
              }}
            />
            <span style={{ fontSize: "0.75rem", color: "var(--muted)" }}>{point.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
