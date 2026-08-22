// Sections whose real content lands in a later session.
//
// These exist so the shell's routing, nav highlighting and keyboard order can
// be built and tested as one piece in S2, rather than being half-verifiable
// until S11. Each states which session fills it in, so an empty screen reads as
// scheduled work rather than something broken.

import { SectionHeader } from "../components/SectionHeader";

export function Placeholder({
  eyebrow,
  title,
  intro,
  session,
}: {
  eyebrow: string;
  title: string;
  intro: string;
  session: string;
}) {
  return (
    <section aria-labelledby="section-title">
      <SectionHeader eyebrow={eyebrow} title={title} intro={intro} />
      <p className="placeholder-note">
        This section is scheduled for {session} — see <code>design/REDESIGN_PLAN.md</code>.
      </p>
    </section>
  );
}
