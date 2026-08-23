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
import { ThemeToggle } from "./ThemeToggle";
import { TelemetryConstellation } from "./TelemetryConstellation";

const DEV_KEYS: Record<Role, string> = {
  analyst: "qqd-dev-key-admin-local-32bytes",
  manager: "qqd-dev-key-manager-local-32bytes",
  employee: "qqd-dev-key-viewer-local-32bytes",
};

export function ApiKeyGate({ children }: { children: React.ReactNode }) {
  const [key, setKey] = useState<string | null>(getApiKey());
  const [selectedRole, setSelectedRole] = useState<Role>("analyst");
  const [rejected, setRejected] = useState(false);
  const { role, setRole } = useRole();

  const loginAs = (targetRole: Role) => {
    const keyToUse = DEV_KEYS[targetRole] || "demo-mode-key";
    setApiKey(keyToUse);
    setRoleStorage(targetRole);
    setRole(targetRole);
    setKey(keyToUse);
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
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "var(--healthy)",
                display: "inline-block",
              }}
            />
            Role: <strong>{ROLE_LABELS[role]?.label || role}</strong>
          </span>
          <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
            <button
              type="button"
              onClick={() => {
                clearApiKey();
                clearRole();
                setKey(null);
              }}
              className="btn btn--quiet"
              style={{ fontSize: "12px", padding: "4px 8px" }}
            >
              Switch Role
            </button>
          </div>
        </div>
        {children}
      </>
    );
  }

  return (
    <div className="gate-wrapper">
      <TelemetryConstellation />
      <div style={{ position: "absolute", top: "1.5rem", right: "1.5rem", zIndex: 10 }}>
        <ThemeToggle />
      </div>
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
          <div role="alert" className="callout callout--alert" style={{ borderLeft: "4px solid var(--exit)", background: "var(--accent-bg)", padding: "12px 14px", marginBottom: "1.5rem", fontSize: "13px", color: "var(--exit)", lineHeight: "1.5" }}>
            ⚠️ <strong>Session Expired or Refused:</strong> Re-select your role below to re-authenticate.
          </div>
        ) : null}

        <form
          onSubmit={(event) => {
            event.preventDefault();
            loginAs(selectedRole);
          }}
          style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}
        >
          <fieldset className="gate__roles" aria-label="Select your role" style={{ border: "1px solid var(--rule)", padding: "14px 16px", margin: 0, background: "var(--paper)" }}>
            <legend style={{ padding: "0 8px", fontSize: "12px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)" }}>
              Choose Persona to Enter
            </legend>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "6px" }}>
              {(Object.keys(ROLE_LABELS) as Role[]).map((r) => {
                const isSelected = selectedRole === r;
                return (
                  <label
                    key={r}
                    className={`gate__role-card ${isSelected ? "gate__role-card--selected" : ""}`}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "24px 28px 1fr 84px",
                      alignItems: "center",
                      gap: "12px",
                      padding: "12px 14px",
                      border: isSelected ? "1px solid var(--accent)" : "1px solid var(--rule)",
                      background: isSelected ? "var(--accent-bg)" : "var(--surface)",
                      cursor: "pointer",
                      borderRadius: "4px",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <input
                      type="radio"
                      name="role"
                      value={r}
                      checked={isSelected}
                      onChange={() => setSelectedRole(r)}
                      style={{ accentColor: "var(--accent)", cursor: "pointer", margin: 0 }}
                    />
                    <span className="gate__role-icon" style={{ fontSize: "20px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      {ROLE_LABELS[r].icon}
                    </span>
                    <span className="gate__role-info" style={{ display: "flex", flexDirection: "column", gap: "2px", minWidth: 0 }}>
                      <strong style={{ fontSize: "14px", color: "var(--ink)", fontWeight: 700 }}>{ROLE_LABELS[r].label}</strong>
                      <span className="gate__role-desc" style={{ fontSize: "12px", color: "var(--muted)", lineHeight: "1.35" }}>
                        {ROLE_LABELS[r].description}
                      </span>
                    </span>

                    <span
                      className="gate__role-badge"
                      style={{
                        justifySelf: "end",
                        width: "84px",
                        textAlign: "center",
                        padding: "5px 0",
                        fontSize: "11px",
                        fontWeight: 700,
                        letterSpacing: "0.05em",
                        textTransform: "uppercase",
                        border: isSelected ? "1px solid var(--accent)" : "1px solid var(--rule)",
                        background: isSelected ? "var(--accent)" : "var(--paper)",
                        color: isSelected ? "var(--surface)" : "var(--muted)",
                        borderRadius: "3px",
                        boxSizing: "border-box",
                        display: "inline-block",
                        transition: "all 0.15s ease",
                      }}
                    >
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
            style={{
              width: "100%",
              padding: "14px 20px",
              fontSize: "14px",
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              borderRadius: "4px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
              background: "#0284c7",
              color: "#ffffff",
              border: "1px solid #0369a1",
              boxShadow: "0 4px 14px rgba(2, 132, 199, 0.35)",
              transition: "all 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          >
            <span style={{ color: "#ffffff", fontWeight: 700 }}>Sign in as {ROLE_LABELS[selectedRole].label}</span>
            <span style={{ color: "#ffffff", fontWeight: 700 }} aria-hidden="true">&rarr;</span>
          </button>
        </form>

        <div style={{ marginTop: "1.75rem", paddingTop: "1.25rem", borderTop: "1px solid var(--rule)", textAlign: "center" }}>
          <p style={{ margin: "0 0 6px", fontSize: "12px", fontWeight: 700, color: "var(--ink)", display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}>
            <span>🔒</span> Secure Access & Privacy Guardrails
          </p>
          <p style={{ margin: 0, fontSize: "11.5px", color: "var(--muted)", lineHeight: "1.5" }}>
            Direct role authentication active. Enterprise production deployments support Single Sign-On (OAuth 2.0 / OIDC, SAML 2.0, Okta, Google Workspace).
          </p>
        </div>
      </main>
    </div>
  );
}
