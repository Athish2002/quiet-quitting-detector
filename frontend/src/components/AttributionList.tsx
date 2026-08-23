

interface AttributionListProps {
  items: string[];
}

export function AttributionList({ items }: AttributionListProps) {
  if (!items || items.length === 0) return null;
  return (
    <section aria-label="Attributions" style={{ marginBottom: "1rem" }}>
      <h3 style={{ marginBottom: "0.5rem", color: "var(--ink)" }}>Attributions</h3>
      <ul style={{ paddingLeft: "1.2rem" }}>
        {items.map((item, idx) => (
          <li key={idx} style={{ color: "var(--muted)" }}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
