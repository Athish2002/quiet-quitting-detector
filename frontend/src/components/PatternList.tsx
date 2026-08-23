

interface PatternListProps {
  patterns: { name: string; description?: string }[];
}

export function PatternList({ patterns }: PatternListProps) {
  if (!patterns || patterns.length === 0) return null;
  return (
    <section aria-label="Patterns" style={{ marginBottom: "1rem" }}>
      <h3 style={{ marginBottom: "0.5rem", color: "var(--ink)" }}>Patterns</h3>
      <ul style={{ paddingLeft: "1.2rem" }}>
        {patterns.map((p, idx) => (
          <li key={idx} style={{ color: "var(--muted)" }}>
            <strong>{p.name}</strong>{p.description ? `: ${p.description}` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}
