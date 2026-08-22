// The opening of every section: an uppercase accent eyebrow, an h1, an
// optional intro capped at ~70ch, and a 2px rule under the lot.
//
// Extracted on the first use rather than the third because eight sections all
// open this way, and the alternative is eight slightly different headers that
// drift apart as they are each edited.

export function SectionHeader({
  eyebrow,
  title,
  intro,
  wide = false,
}: {
  eyebrow: string;
  title: string;
  intro?: string;
  /** Overview's h1 is 44px and deliberately narrow; every other section is 38px. */
  wide?: boolean;
}) {
  return (
    <header className={wide ? "section-head section-head--wide" : "section-head"}>
      <p className="section-head__eyebrow">{eyebrow}</p>
      {/* One section renders at a time, so a stable id is safe and lets each
          section label itself without every caller inventing one. */}
      <h1 id="section-title" className="section-head__title">
        {title}
      </h1>
      {intro ? <p className="section-head__intro">{intro}</p> : null}
    </header>
  );
}
