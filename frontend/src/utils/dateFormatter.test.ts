// frontend/src/utils/dateFormatter.test.ts

import { describe, expect, it } from "vitest";
import { formatShortDateTime, formatDateOnly, formatTimeOnly } from "./dateFormatter";

describe("dateFormatter", () => {
  it("formats ISO string with microseconds into short localized string without microseconds", () => {
    const raw = "2026-08-22T17:57:57.978648+00:00";
    const formatted = formatShortDateTime(raw);

    expect(formatted).not.toContain("978648");
    expect(formatted).not.toContain("+00:00");
    expect(formatted).toMatch(/2026/);
    expect(formatted).toMatch(/Aug|08/);
  });

  it("handles null and undefined gracefully", () => {
    expect(formatShortDateTime(null)).toBe("—");
    expect(formatShortDateTime(undefined)).toBe("—");
    expect(formatDateOnly(undefined)).toBe("—");
    expect(formatTimeOnly(undefined)).toBe("—");
  });

  it("formats date only correctly", () => {
    const raw = "2026-08-22T17:57:57.978648Z";
    const formatted = formatDateOnly(raw);

    expect(formatted).toMatch(/2026/);
    expect(formatted).toMatch(/22/);
  });
});
