// Shared error rendering.
//
// CONTEXT.md rule 4: never surface a raw provider error. `ApiError` carries only
// the server's safe title from the RFC 9457 problem document; anything else
// becomes a generic message rather than whatever string happened to be thrown.
// A stack trace here would contain employee names.

import { ApiError } from "../api/client";

export function ErrorNote({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError
      ? error.message
      : "Something went wrong. Please try again.";
  const correlation = error instanceof ApiError ? error.correlationId : undefined;

  return (
    <p role="alert" className="callout callout--alert">
      {message}
      {correlation ? ` (reference ${correlation})` : null}
    </p>
  );
}
