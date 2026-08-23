// frontend/src/contexts/RoleContext.test.tsx

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import { RoleProvider, useRole, clearRole, setRoleStorage, getRole } from "./RoleContext";

function TestComponent() {
  const { role, setRole, hasAccess } = useRole();

  return (
    <div>
      <p data-testid="current-role">{role ?? "none"}</p>
      <p data-testid="can-access-diagnostic">
        {hasAccess("diagnostic") ? "yes" : "no"}
      </p>
      <p data-testid="can-access-cohort">
        {hasAccess("cohort") ? "yes" : "no"}
      </p>
      <button onClick={() => setRole("manager")}>Set Manager</button>
      <button onClick={() => setRole("employee")}>Set Employee</button>
      <button onClick={() => setRole("analyst")}>Set Analyst</button>
    </div>
  );
}

describe("RoleContext", () => {
  beforeEach(() => {
    clearRole();
  });

  it("defaults to null when no role is in storage and provider is used", () => {
    render(
      <RoleProvider>
        <TestComponent />
      </RoleProvider>,
    );

    expect(screen.getByTestId("current-role")).toHaveTextContent("none");
    expect(screen.getByTestId("can-access-diagnostic")).toHaveTextContent("no");
  });

  it("updates role and access permissions when changed", () => {
    render(
      <RoleProvider>
        <TestComponent />
      </RoleProvider>,
    );

    // Switch to analyst
    fireEvent.click(screen.getByText("Set Analyst"));
    expect(screen.getByTestId("current-role")).toHaveTextContent("analyst");
    expect(screen.getByTestId("can-access-diagnostic")).toHaveTextContent("yes");
    expect(screen.getByTestId("can-access-cohort")).toHaveTextContent("yes");
    expect(getRole()).toBe("analyst");

    // Switch to manager
    fireEvent.click(screen.getByText("Set Manager"));
    expect(screen.getByTestId("current-role")).toHaveTextContent("manager");
    expect(screen.getByTestId("can-access-diagnostic")).toHaveTextContent("no");
    expect(screen.getByTestId("can-access-cohort")).toHaveTextContent("yes");
    expect(getRole()).toBe("manager");

    // Switch to employee
    fireEvent.click(screen.getByText("Set Employee"));
    expect(screen.getByTestId("current-role")).toHaveTextContent("employee");
    expect(screen.getByTestId("can-access-diagnostic")).toHaveTextContent("no");
    expect(screen.getByTestId("can-access-cohort")).toHaveTextContent("no");
    expect(getRole()).toBe("employee");
  });

  it("initializes from sessionStorage if set", () => {
    setRoleStorage("manager");

    render(
      <RoleProvider>
        <TestComponent />
      </RoleProvider>,
    );

    expect(screen.getByTestId("current-role")).toHaveTextContent("manager");
  });
});
