// frontend/src/components/ApiKeyGate.tsx
//
// Modernist Authentication & Role Gate.
// - Centered, spacious Modernist authentication card
// - Interactive role selector with clear boundaries (Analyst / Manager / Employee)
// - "⚡ Auto-Fill Dev Key" helper for instant 1-click local access
// - Show/Hide password toggle
// - High-contrast accessible typography

import { useEffect, useState } from "react";
import {
  AUTH_FAILED_EVENT,
  clearApiKey,
  getApiKey,
  setApiKey,
} from "../api/client";
import {
  type Role,
  ROLE_LABELS,
  setRoleStorage,
  clearRole,
  useRole,
} from "../contexts/RoleContext";

const DEV_KEYS: Record<Role, string> = {
  analyst: "qqd-dev-key-admin-local-32bytes",
  manager: "qqd-dev-key-manager-local-32bytes",
  employee: "qqd-dev-key-viewer-local-32bytes",
};

export function ApiKeyGate({ children }: { children: React.ReactNode }) {
  const [key, setKey] = useState<string | null>(getApiKey());
  const [draft, setDraft] = useState("");
  const [selectedRole, setSelectedRole] = useState<Role>("analyst");
  const [rejected, setRejected] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const { role, setRole } = useRole();

  const handleRoleChange = (newRole: Role) => {
    setSelectedRole(newRole);
    // If draft is empty or is one of the dev keys, update it to the matching key for this role
    if (!draft || Object.values(DEV_KEYS).includes(draft)) {
      setDraft(DEV_KEYS[newRole]);
    }
  };

  const handleAutoFill = () => {
    setDraft(DEV_KEYS[selectedRole]);
  };

  useEffect(() => {
    const onAuthFailed = () => {
      setKey(null);
      setRejected(true);
    };
    window.addEventListener(AUTH_FAILED_EVENT, onAuthFailed);
    return () => window.removeEventListener(AUTH_FAILED_EVENT, onAuthFailed);
  }, []);

  if (key && role) {
    return (
      <>
        <div className="keybar">
          <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span className="keybar__role-badge">
              {ROLE_LABELS[role].icon} {ROLE_LABELS[role].label}
            </span>
            <span style={{ color: "var(--muted)" }}>· Authenticated tab</span>
          </span>
          <button
            type="button"
            className="btn btn--glass"
            style={{ padding: "4px 10px", fontSize: "12px", background: "transparent", border: "1px solid var(--rule)", cursor: "pointer", color: "var(--ink)" }}
            onClick={() => {
              clearApiKey();
              clearRole();
              setKey(null);
            }}
          >
            Sign out
          </button>
        </div>
        {children}
      </>
    );
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "3rem 1.5rem",
        background: "var(--paper)",
      }}
    >
      <main
        className="gate"
        style={{
          width: "100%",
          maxWidth: "580px",
          margin: "0 auto",
          padding: "2.75rem 2.5rem",
          background: "var(--surface)",
          border: "1px solid var(--rule)",
          boxShadow: "0 14px 40px rgba(0, 0, 0, 0.09)",
        }}
      >
        <div className="gate__brand" style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: "48px", height: "48px", background: "var(--accent-bg)", color: "var(--accent)", fontSize: "24px", marginBottom: "12px" }}>
            ⚖️
          </div>
          <h1 className="gate__title" style={{ margin: "0 0 6px", fontSize: "26px", fontFamily: "var(--font-heading)", color: "var(--ink)", letterSpacing: "-0.02em" }}>
            Quiet-Quitting Detector
          </h1>
          <p className="gate__strapline" style={{ margin: 0, fontSize: "12.5px", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 600 }}>
            Wellbeing Prompt · Not a Verdict
          </p>
        </div>

        {rejected ? (
          <div role="alert" className="callout callout--alert" style={{ borderLeft: "4px solid var(--exit)", background: "var(--accent-bg)", padding: "12px 14px", marginBottom: "1.5rem", fontSize: "13.5px", color: "var(--exit)", lineHeight: "1.5" }}>
            ⚠️ <strong>Authentication Refused:</strong> Token was not accepted by the backend. Click <strong>Auto-Fill Dev Key</strong> below to load the active local key.
          </div>
        ) : null}

        <form
          onSubmit={(event) => {
            event.preventDefault();
            const trimmed = draft.trim();
            if (!trimmed) return;
            setApiKey(trimmed);
            setRoleStorage(selectedRole);
            setRole(selectedRole);
            setKey(trimmed);
          }}
          style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}
        >
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <label htmlFor="api-key" style={{ fontSize: "13px", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--ink)" }}>
                API Key
              </label>
              <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                <button
                  type="button"
                  onClick={handleAutoFill}
                  style={{
                    background: "var(--accent-bg)",
                    border: "1px solid var(--accent)",
                    color: "var(--accent)",
                    fontSize: "12px",
                    fontWeight: 700,
                    padding: "4px 10px",
                    cursor: "pointer",
                  }}
                >
                  ⚡ Auto-Fill Dev Key
                </button>
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  style={{ background: "transparent", border: "none", color: "var(--muted)", fontSize: "12px", cursor: "pointer", textDecoration: "underline" }}
                >
                  {showKey ? "Hide" : "Show"}
                </button>
              </div>
            </div>
            <div style={{ position: "relative" }}>
              <input
                id="api-key"
                name="api-key"
                type={showKey ? "text" : "password"}
                autoComplete="off"
                placeholder="Paste your API key here..."
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                aria-describedby="api-key-help"
                style={{
                  width: "100%",
                  padding: "12px 14px",
                  fontSize: "14px",
                  border: "1px solid var(--rule)",
                  background: "var(--paper)",
                  color: "var(--ink)",
                  boxSizing: "border-box",
                }}
                required
              />
            </div>
            <p id="api-key-help" className="hint" style={{ margin: "8px 0 0", fontSize: "12px", color: "var(--muted)", lineHeight: "1.5" }}>
              If you are running the server locally, click <strong>Auto-Fill Dev Key</strong> or check the terminal startup logs.
            </p>
          </div>

          <fieldset className="gate__roles" aria-label="Select your role" style={{ border: "1px solid var(--rule)", padding: "14px 16px", margin: 0, background: "var(--paper)" }}>
            <legend style={{ padding: "0 8px", fontSize: "12px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)" }}>
              Sign in as
            </legend>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "6px" }}>
              {(Object.keys(ROLE_LABELS) as Role[]).map((r) => {
                const isSelected = selectedRole === r;
                return (
                  <label
                    key={r}
                    className={`gate__role-card ${isSelected ? "gate__role-card--selected" : ""}`}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "12px",
                      padding: "12px 14px",
                      border: "1px solid",
                      borderColor: isSelected ? "var(--accent)" : "var(--rule)",
                      background: isSelected ? "var(--accent-bg)" : "var(--surface)",
                      cursor: "pointer",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <input
                      type="radio"
                      name="role"
                      value={r}
                      checked={isSelected}
                      onChange={() => handleRoleChange(r)}
                      style={{ marginTop: "4px", accentColor: "var(--accent)" }}
                    />
                    <span className="gate__role-icon" style={{ fontSize: "20px", lineHeight: "1.2" }}>
                      {ROLE_LABELS[r].icon}
                    </span>
                    <span className="gate__role-info" style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                      <strong style={{ fontSize: "14px", color: "var(--ink)" }}>{ROLE_LABELS[r].label}</strong>
                      <span className="gate__role-desc" style={{ fontSize: "12.5px", color: "var(--muted)", lineHeight: "1.4" }}>
                        {ROLE_LABELS[r].description}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <button
            type="submit"
            className="btn btn--primary"
            disabled={!draft.trim()}
            style={{
              padding: "14px 24px",
              fontSize: "15px",
              fontWeight: 700,
              letterSpacing: "0.02em",
              background: draft.trim() ? "var(--ink)" : "#6B7280",
              color: "#FFFFFF",
              border: "none",
              cursor: draft.trim() ? "pointer" : "not-allowed",
              boxShadow: draft.trim() ? "0 4px 16px rgba(0,0,0,0.15)" : "none",
              transition: "all 0.2s ease",
            }}
          >
            Sign in as {ROLE_LABELS[selectedRole].label} &rarr;
          </button>
        </form>

        <p className="gate__footer" style={{ margin: "1.75rem 0 0", fontSize: "12px", color: "var(--muted)", textAlign: "center", lineHeight: "1.5" }}>
          Key is securely maintained in sessionStorage for this active browser tab and forgotten upon tab close.
        </p>
      </main>
    </div>
  );
}
