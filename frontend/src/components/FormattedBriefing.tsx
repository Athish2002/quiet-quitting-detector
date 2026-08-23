// frontend/src/components/FormattedBriefing.tsx
//
// Formats raw manager briefing markdown text into structured, elegant Modernist UI cards.
// Parses out:
// - Signals Detected
// - Pre-Meeting Observation
// - Supportive Things to Say (Green/Accent prompt box)
// - Things Never to Say (Cautionary guide box)
// - Evidence-Based Actions (Numbered action cards)
// Robust against both Markdown headers (###), bold headers (**...**), and plain text headers (Header:).

interface FormattedBriefingProps {
  text: string;
}

interface ParsedSection {
  title: string;
  type: "signals" | "observation" | "to_say" | "never_say" | "actions" | "general";
  content: string[];
}

function cleanText(str: string): string {
  return str
    .replace(/^[-*•]\s*/, "")
    .replace(/^\d+\.\s*/, "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/---/g, "")
    .trim();
}

function parseBriefing(rawText: string): ParsedSection[] {
  if (!rawText) return [];

  const lines = rawText.split("\n").map((l) => l.trim()).filter(Boolean);
  const sections: ParsedSection[] = [];
  let currentSection: ParsedSection | null = null;

  const isHeader = (line: string): { isHeader: boolean; title: string; type: ParsedSection["type"] } => {
    const clean = line.replace(/^[#*\s-]+/, "").replace(/[*#:]+$/g, "").trim();
    const lower = clean.toLowerCase();

    if (lower.startsWith("manager briefing")) {
      return { isHeader: true, title: "Overview", type: "general" };
    }
    if (lower.includes("signal") || lower.includes("behavioral pattern")) {
      return { isHeader: true, title: "Signals Detected", type: "signals" };
    }
    if (lower.includes("observation") || lower.includes("pre-meeting")) {
      return { isHeader: true, title: "Pre-Meeting Observation", type: "observation" };
    }
    if (lower.includes("never") || lower.includes("avoid")) {
      return { isHeader: true, title: "Things Never to Say", type: "never_say" };
    }
    if (lower.includes("to say") || lower.includes("supportive")) {
      return { isHeader: true, title: "3 Supportive Things to Say", type: "to_say" };
    }
    if (lower.includes("action") || lower.includes("intervention") || lower.includes("evidence-based")) {
      return { isHeader: true, title: "Evidence-Based Actions", type: "actions" };
    }
    return { isHeader: false, title: "", type: "general" };
  };

  for (const line of lines) {
    const headerCheck = isHeader(line);

    // If it's a known header and not a long paragraph
    if (headerCheck.isHeader && line.length < 80) {
      if (currentSection && currentSection.content.length > 0) {
        sections.push(currentSection);
      }
      currentSection = {
        title: headerCheck.title,
        type: headerCheck.type,
        content: [],
      };
    } else {
      if (!currentSection) {
        currentSection = {
          title: "Signals Detected",
          type: "signals",
          content: [],
        };
      }
      const cleaned = cleanText(line);
      if (cleaned) {
        currentSection.content.push(cleaned);
      }
    }
  }

  if (currentSection && currentSection.content.length > 0) {
    sections.push(currentSection);
  }

  // Filter out empty overview headers if any
  return sections.filter((s) => s.content.length > 0);
}

export function FormattedBriefing({ text }: FormattedBriefingProps) {
  if (!text) return null;

  const sections = parseBriefing(text);

  if (sections.length === 0) {
    return <p className="briefing-card__text">{text}</p>;
  }

  return (
    <div className="formatted-briefing" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {sections.map((sec, idx) => {
        if (sec.type === "to_say") {
          return (
            <div
              key={idx}
              className="briefing-block briefing-block--to-say"
              style={{
                background: "var(--surface)",
                border: "1px solid var(--healthy)",
                borderLeft: "4px solid var(--healthy)",
                padding: "1.25rem",
              }}
            >
              <h3 style={{ margin: "0 0 10px", fontSize: "13px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--healthy)", display: "flex", alignItems: "center", gap: "6px" }}>
                <span>💬</span> {sec.title}
              </h3>
              <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "flex", flexDirection: "column", gap: "10px", fontSize: "14px", lineHeight: "1.6", color: "var(--ink)" }}>
                {sec.content.map((item, i) => {
                  const unquoted = item.replace(/^["']|["']$/g, "").trim();
                  return (
                    <li key={i}>
                      <em>&ldquo;{unquoted}&rdquo;</em>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        }

        if (sec.type === "never_say") {
          return (
            <div
              key={idx}
              className="briefing-block briefing-block--never-say"
              style={{
                background: "var(--surface)",
                border: "1px solid var(--exit)",
                borderLeft: "4px solid var(--exit)",
                padding: "1.25rem",
              }}
            >
              <h3 style={{ margin: "0 0 10px", fontSize: "13px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--exit)", display: "flex", alignItems: "center", gap: "6px" }}>
                <span>⚠️</span> {sec.title}
              </h3>
              <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "flex", flexDirection: "column", gap: "8px", fontSize: "13.5px", lineHeight: "1.6", color: "var(--ink)" }}>
                {sec.content.map((item, i) => {
                  const unquoted = item.replace(/^["']|["']$/g, "").trim();
                  return (
                    <li key={i}>
                      {unquoted}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        }

        if (sec.type === "actions") {
          return (
            <div
              key={idx}
              className="briefing-block briefing-block--actions"
              style={{
                background: "var(--surface)",
                border: "1px solid var(--rule)",
                padding: "1.25rem",
              }}
            >
              <h3 style={{ margin: "0 0 10px", fontSize: "13px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--accent)", display: "flex", alignItems: "center", gap: "6px" }}>
                <span>📋</span> {sec.title}
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "10px" }}>
                {sec.content.map((item, i) => {
                  const colonIdx = item.indexOf(":");
                  const hasLabel = colonIdx > 0 && colonIdx < 40;
                  const label = hasLabel ? item.substring(0, colonIdx).trim() : `Action ${i + 1}`;
                  const body = hasLabel ? item.substring(colonIdx + 1).trim() : item;

                  return (
                    <div key={i} style={{ padding: "10px 12px", background: "var(--paper)", border: "1px solid var(--rule)", fontSize: "13px", lineHeight: "1.5", color: "var(--ink)" }}>
                      <strong style={{ display: "block", color: "var(--accent)", marginBottom: "4px" }}>
                        {label}
                      </strong>
                      <p style={{ margin: 0, color: "var(--ink)", fontSize: "12.5px" }}>
                        {body}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        }

        return (
          <div
            key={idx}
            className="briefing-block"
            style={{
              background: "var(--surface)",
              border: "1px solid var(--rule)",
              padding: "1.25rem",
            }}
          >
            <h3 style={{ margin: "0 0 8px", fontSize: "13px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)" }}>
              {sec.title}
            </h3>
            <div style={{ fontSize: "14px", lineHeight: "1.6", color: "var(--ink)" }}>
              {sec.content.map((item, i) => (
                <p key={i} style={{ margin: "0 0 6px" }}>
                  {item}
                </p>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
