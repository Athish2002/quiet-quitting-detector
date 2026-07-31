// frontend/src/components/ConfidenceBadge.tsx
//
// The component that keeps §6.1's promise on screen: "Low confidence must
// visibly suppress the strength of the briefing -- the manager sees 'we're not
// sure yet,' not a confident number built on three data points."
//
// The backend already computes confidence and refuses to hide it. This is where
// that survives contact with a user interface, and it is easy to get wrong:
// rendering "6/10" in large type with a small grey "low confidence" label
// underneath technically displays both and communicates only the first.
//
// So at low confidence the score is not rendered as a number at all. A range is
// shown instead, with the caveat in the same visual weight as the finding. If a
// manager takes only the largest text on the screen -- which is what people do
// -- they should still take away something true.

import type { Confidence } from "../api/types";

const LABEL: Record<Confidence, string> = {
  none: "No usable evidence",
  low: "Not sure yet",
  moderate: "Moderate confidence",
  high: "Well evidenced",
};

const EXPLANATION: Record<Confidence, string> = {
  none: "There is not enough of this person's own history to say anything.",
  low: "Based on very little of this person's own history. Treat as a prompt to ask, not a finding.",
  moderate: "Based on a reasonable amount of this person's own history.",
  high: "Based on a substantial run of this person's own history.",
};

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  return (
    <span className={`badge badge--${confidence}`} title={EXPLANATION[confidence]}>
      {LABEL[confidence]}
    </span>
  );
}

export function ScoreDisplay({
  score,
  range,
  confidence,
}: {
  score: number;
  range?: [number, number] | null;
  confidence: Confidence;
}) {
  const suppressed = confidence === "low" || confidence === "none";

  if (suppressed) {
    return (
      <div className="score score--suppressed">
        <p className="score__caveat">
          We are not confident enough to give a single number here.
        </p>
        {range ? (
          <p className="score__range">
            Plausible range <strong>{range[0]}–{range[1]}</strong> out of 10
          </p>
        ) : null}
        <ConfidenceBadge confidence={confidence} />
        <p className="score__footnote">
          This range is a rule-of-thumb band that widens when there is less
          evidence. It is not a statistical confidence interval.
        </p>
      </div>
    );
  }

  return (
    <div className="score">
      <p className="score__value">
        <strong>{score}</strong>
        <span className="score__scale"> / 10</span>
      </p>
      {range ? (
        <p className="score__range">
          Plausible range {range[0]}–{range[1]}
        </p>
      ) : null}
      <ConfidenceBadge confidence={confidence} />
    </div>
  );
}
