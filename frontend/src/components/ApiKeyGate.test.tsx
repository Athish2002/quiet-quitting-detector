// frontend/src/components/ApiKeyGate.test.tsx

import { render, screen, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it, beforeEach } from "vitest";
import { ApiKeyGate } from "./ApiKeyGate";
import { RoleProvider, clearRole } from "../contexts/RoleContext";
import { clearApiKey, setApiKey } from "../api/client";

function renderGate() {
  return render(
    <RoleProvider>
      <ApiKeyGate>
        <div data-testid="protected-content">Dashboard Active</div>
      </ApiKeyGate>
    </RoleProvider>,
  );
}

describe("ApiKeyGate", () => {
  beforeEach(() => {
    clearApiKey();
    clearRole();
  });

  it("shows login form and 3 role selection cards when unauthenticated", () => {
    renderGate();

    expect(screen.getByText("Quiet-Quitting Detector")).toBeInTheDocument();
    expect(screen.getByLabelText(/API key/i)).toBeInTheDocument();
    expect(screen.getByText("Wellbeing Analyst")).toBeInTheDocument();
    expect(screen.getByText("Manager")).toBeInTheDocument();
    expect(screen.getByText("Employee")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sign in/i })).toBeInTheDocument();
    expect(screen.queryByTestId("protected-content")).toBeNull();
  });

  it("signs in when API key is provided and role is chosen", () => {
    renderGate();

    const input = screen.getByLabelText(/API key/i);
    fireEvent.change(input, { target: { value: "test-secret-key" } });

    const managerRadio = screen.getByLabelText(/Manager/i);
    fireEvent.click(managerRadio);

    fireEvent.click(screen.getByRole("button", { name: /Sign in/i }));

    expect(screen.getByTestId("protected-content")).toBeInTheDocument();
    expect(screen.getByText(/Manager/i)).toBeInTheDocument();
    expect(screen.getByText(/Sign out/i)).toBeInTheDocument();
  });

  it("shows content immediately if key and role exist", () => {
    setApiKey("pre-existing-key");
    sessionStorage.setItem("qqd.role", "analyst");

    renderGate();

    expect(screen.getByTestId("protected-content")).toBeInTheDocument();
    expect(screen.getByText(/Wellbeing Analyst/i)).toBeInTheDocument();
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderGate();
    expect((await axe(container)).violations).toEqual([]);
  });
});
