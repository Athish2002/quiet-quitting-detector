

interface InterventionButtonsProps {
  onAccept: () => void;
  onDismiss: () => void;
}

export function InterventionButtons({ onAccept, onDismiss }: InterventionButtonsProps) {
  return (
    <div style={{ marginTop: "1rem", display: "flex", gap: "0.75rem" }}>
      <button
        className="btn btn--primary"
        onClick={onAccept}
        style={{ flex: 1 }}
      >
        Accept
      </button>
      <button
        className="btn btn--quiet"
        onClick={onDismiss}
        style={{ flex: 1 }}
      >
        Dismiss
      </button>
    </div>
  );
}
