// frontend/src/components/ApiKeyGate.tsx
//
// Phase 4 made every route require a key and left the old UI receiving 401s.
// This is the fix on the frontend side.
//
// It is a gate, not a login: there is no session, no cookie, no server-side
// state. The user pastes the key their operator gave them (or the one the
// server printed at startup), it lives in sessionStorage until the tab closes,
// and every request carries it. Real sign-in is OIDC and lands with the
// identity work -- see docs/LIMITATIONS.md.
//
// Deliberately does not tell the user whether a key was wrong versus missing;
// that mirrors the server, which returns 401 for both so an attacker learns
// nothing from the difference.

import { useEffect, useState } from "react";
import {
  AUTH_FAILED_EVENT,
  clearApiKey,
  getApiKey,
  setApiKey,
} from "../api/client";

export function ApiKeyGate({ children }: { children: React.ReactNode }) {
  const [key, setKey] = useState<string | null>(getApiKey());
  const [draft, setDraft] = useState("");
  const [rejected, setRejected] = useState(false);

  useEffect(() => {
    const onAuthFailed = () => {
      setKey(null);
      setRejected(true);
    };
    window.addEventListener(AUTH_FAILED_EVENT, onAuthFailed);
    return () => window.removeEventListener(AUTH_FAILED_EVENT, onAuthFailed);
  }, []);

  if (key) {
    return (
      <>
        <div className="keybar">
          <span>Signed in with an API key for this tab only.</span>
          <button
            type="button"
            onClick={() => {
              clearApiKey();
              setKey(null);
            }}
          >
            Forget key
          </button>
        </div>
        {children}
      </>
    );
  }

  return (
    <main className="gate">
      <h1>Enter your API key</h1>
      {rejected ? (
        // Says the key did not work, and nothing more. The server returns 401
        // for both a missing and a wrong key so an attacker learns nothing from
        // the difference; saying more here would give it back.
        <p role="alert" className="callout callout--alert">
          That key was not accepted. Please check it and try again.
        </p>
      ) : null}
      <p>
        This dashboard shows information about real people, so every request is
        authenticated. Your key is kept for this browser tab only and is
        forgotten when you close it.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const trimmed = draft.trim();
          if (!trimmed) return;
          setApiKey(trimmed);
          setKey(trimmed);
        }}
      >
        <label htmlFor="api-key">API key</label>
        <input
          id="api-key"
          name="api-key"
          type="password"
          autoComplete="off"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          aria-describedby="api-key-help"
        />
        <p id="api-key-help" className="hint">
          If you are running the server locally it printed a temporary key at
          startup.
        </p>
        <button type="submit" disabled={!draft.trim()}>
          Continue
        </button>
      </form>
    </main>
  );
}
