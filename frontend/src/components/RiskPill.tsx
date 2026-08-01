// A person's current assessment, in one element.
//
// The rule this component encodes: at low confidence the NUMBER IS NOT SHOWN.
// A pill reading "At Risk 7/10" next to a small grey "low confidence" label
// technically displays both and communicates only the first, and the number is
// what a manager repeats in a meeting.
//
// Colour is never the only carrier of meaning -- the classification is spelled
// out in text (WCAG 1.4.1), because a red dot is invisible to a screen reader
// and ambiguous to a colour-blind reader.

import type { Classification, Confidence } from "../api/types";

const SLUG: Record<Classification, string> = {
  Healthy: "healthy",
  Watch: "watch",
  "At Risk": "at-risk",
  "Silent Exit": "silent-exit",
};

export function RiskPill({
  classification,
  score,
  confidence,
}: {
  classification: Classification;
  score: number;
  confidence: Confidence | null;
}) {
  const thin = confidence === "low" || confidence === "none";

  return (
    <span className={`pill pill--${SLUG[classification] ?? "healthy"}`}>
      {classification}
      {thin ? (
        <span className="pill__caveat"> — not enough evidence for a score</span>
      ) : (
        <span className="pill__score"> {score}/10</span>
      )}
    </span>
  );
}
