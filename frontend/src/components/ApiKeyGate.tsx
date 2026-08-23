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
import { BrandSymbol } from "./BrandSymbol";

const DEV_KEYS: Record<Role, string> = {
  analyst: "qqd-dev-key-admin-local-32bytes",
  manager: "qqd-dev-key-manager-local-32bytes",
  employee: "qqd-dev-key-viewer-local-32bytes",
};

export function ApiKeyGate({ children }: { children: React.ReactNode }) {
  const [key, setKey] = useState<string | null>(getApiKey());
  const [draft, setDraft] = useState(DEV_KEYS.analyst);
  const [selectedRole, setSelectedRole] = useState<Role>("analyst");
  const [rejected, setRejected] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const { role, setRole } = useRole();

  const loginAs = (targetRole: Role) => {
    const keyToUse = draft.trim() || DEV_KEYS[targetRole] || "demo-mode-key";
    setApiKey(keyToUse);
    setRoleStorage(targetRole);
    setRole(targetRole);
    setKey(keyToUse);
  };

  const handleRoleChange = (newRole: Role) => {
    setSelectedRole(newRole);
    setDraft(DEV_KEYS[newRole]);
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
    <div className="gate-wrapper">
      <main className="gate gate-card-animated">
        <div className="gate__brand" style={{ textAlign: "center", marginBottom: "1.75rem" }}>
          <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", marginBottom: "12px", cursor: "pointer" }}>
            <BrandSymbol size={58} interactive={true} animate={true} />
          </div>
          <h1 className="gate__title" style={{ margin: "0 0 6px", fontSize: "26px", fontFamily: "var(--font-heading)", color: "var(--ink)", letterSpacing: "-0.02em" }}>
            Quiet-Quitting Detector
          </h1>
          <p className="gate__strapline" style={{ margin: 0, fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 600 }}>
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
            loginAs(selectedRole);
          }}
          style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}
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
                className="gate__input-field"
                required
              />
            </div>
            <p id="api-key-help" className="hint" style={{ margin: "6px 0 0", fontSize: "12px", color: "var(--muted)", lineHeight: "1.4" }}>
              Pre-filled with local dev key. Click any role or button to enter.
            </p>
          </div>

          <fieldset className="gate__roles" aria-label="Select your role" style={{ border: "1px solid var(--rule)", padding: "12px 14px", margin: 0, background: "var(--paper)" }}>
            <legend style={{ padding: "0 8px", fontSize: "12px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)" }}>
              Sign in as
            </legend>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "4px" }}>
              {(Object.keys(ROLE_LABELS) as Role[]).map((r) => {
                const isSelected = selectedRole === r;
                return (
                  <label
                    key={r}
                    className={`gate__role-card ${isSelected ? "gate__role-card--selected" : ""}`}
                  >
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "10px" }}>
                      <input
                        type="radio"
                        name="role"
                        value={r}
                        checked={isSelected}
                        onChange={() => handleRoleChange(r)}
                        style={{ marginTop: "3px", accentColor: "var(--accent)", cursor: "pointer" }}
                      />
                      <span className="gate__role-icon">
                        {ROLE_LABELS[r].icon}
                      </span>
                      <span className="gate__role-info">
                        <strong>{ROLE_LABELS[r].label}</strong>
                        <span className="gate__role-desc">
                          {ROLE_LABELS[r].description}
                        </span>
                      </span>
                    </div>

                    <span className="gate__role-badge">
                      {isSelected ? "Active ✓" : "Select"}
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <button
            type="submit"
            className="btn btn--primary gate__submit-btn"
            disabled={!draft.trim()}
          >
            Sign in as {ROLE_LABELS[selectedRole].label} &rarr;
          </button>
        </form>

        <p className="gate__footer" style={{ margin: "1.5rem 0 0", fontSize: "12px", color: "var(--muted)", textAlign: "center", lineHeight: "1.5" }}>
          Key is securely maintained in sessionStorage for this active browser tab and forgotten upon tab close.
        </p>
      </main>
    </div>
  );
}
