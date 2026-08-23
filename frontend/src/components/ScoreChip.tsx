

interface ScoreChipProps {
  confidence: number;
}

export function ScoreChip({ confidence }: ScoreChipProps) {
  const percent = Math.round(confidence * 100);
  const bg = confidence > 0.5 ? "var(--ok-bg)" : "var(--caveat-bg)";
  const color = confidence > 0.5 ? "var(--ok)" : "var(--caveat-ink)";
  return (
    <div
      style={{
        background: bg,
        color,
        padding: "0.2rem 0.6rem",
        borderRadius: "var(--radius)",
        fontWeight: 600,
        fontSize: "0.85rem",
        display: "inline-block",
      }}
    >
      Confidence: {percent}%
    </div>
  );
}
