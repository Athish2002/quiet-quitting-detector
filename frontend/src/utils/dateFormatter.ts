// frontend/src/utils/dateFormatter.ts
//
// Dynamic, client-side localized date/time formatting.
//
// Always uses the browser's local timezone so a user in London, Tokyo, or New York
// sees times formatted according to their own system clock and locale, rather than
// raw UTC ISO strings (e.g. 2026-08-22T17:57:57.978648+00:00) or hardcoded offsets.

/**
 * Formats an ISO string or timestamp into a compact, localized date and time string.
 * Example output: "22 Aug 2026, 17:57:36" (or locale equivalent)
 */
export function formatShortDateTime(isoOrTimestamp: string | number | undefined | null): string {
  if (!isoOrTimestamp) return "—";

  try {
    const date = new Date(isoOrTimestamp);
    if (isNaN(date.getTime())) {
      // If parsing as Date fails, return trimmed original string up to seconds
      return String(isoOrTimestamp).replace("T", " ").replace(/\.\d+.*$/, "");
    }

    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(date);
  } catch {
    return String(isoOrTimestamp);
  }
}

/**
 * Formats an ISO string into date only (e.g. "22 Aug 2026").
 */
export function formatDateOnly(isoOrTimestamp: string | number | undefined | null): string {
  if (!isoOrTimestamp) return "—";

  try {
    const date = new Date(isoOrTimestamp);
    if (isNaN(date.getTime())) return String(isoOrTimestamp);

    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(date);
  } catch {
    return String(isoOrTimestamp);
  }
}

/**
 * Formats an ISO string into time only (e.g. "17:57:36").
 */
export function formatTimeOnly(isoOrTimestamp: string | number | undefined | null): string {
  if (!isoOrTimestamp) return "—";

  try {
    const date = new Date(isoOrTimestamp);
    if (isNaN(date.getTime())) return String(isoOrTimestamp);

    return new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(date);
  } catch {
    return String(isoOrTimestamp);
  }
}
