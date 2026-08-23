// frontend/src/components/WelcomeState.test.tsx

import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { WelcomeState } from "./WelcomeState";

function renderWelcomeState(role: "analyst" | "manager" | "employee") {
  return render(
    <MemoryRouter>
      <WelcomeState role={role} />
    </MemoryRouter>,
  );
}

describe("WelcomeState", () => {
  describe("analyst role", () => {
    it("renders heading, subtext, 3 step cards, and link to /ingest", () => {
      const { container } = renderWelcomeState("analyst");

      const root = container.querySelector(".welcome-state");
      expect(root).toBeInTheDocument();

      const heading = container.querySelector("h2.welcome-state__heading");
      expect(heading).toHaveTextContent("Welcome to the Quiet-Quitting Detector");

      const text = container.querySelector("p.welcome-state__text");
      expect(text).toHaveTextContent(
        "This system identifies sustained divergence from an employee's own baseline and drafts supportive manager briefings. It never ranks people or recommends disciplinary action.",
      );

      const stepsList = container.querySelector(".welcome-state__steps");
      expect(stepsList).toBeInTheDocument();
      expect(stepsList).toHaveClass("welcome-steps");

      const steps = Array.from(container.querySelectorAll(".welcome-step"));
      expect(steps).toHaveLength(3);

      // Step 1
      const step1Num = steps[0]?.querySelector(".welcome-step__number");
      const step1Title = steps[0]?.querySelector(".welcome-step__title");
      const step1Body = steps[0]?.querySelector(".welcome-step__body");
      expect(step1Num).toHaveTextContent("Step 1");
      expect(step1Title).toHaveTextContent("Ingest data");
      expect(step1Body).toHaveTextContent(
        "Upload a week of telemetry to begin. CSV, JSON, or direct database connection.",
      );

      // Step 2
      const step2Num = steps[1]?.querySelector(".welcome-step__number");
      const step2Title = steps[1]?.querySelector(".welcome-step__title");
      const step2Body = steps[1]?.querySelector(".welcome-step__body");
      expect(step2Num).toHaveTextContent("Step 2");
      expect(step2Title).toHaveTextContent("Run the pipeline");
      expect(step2Body).toHaveTextContent(
        "The system evaluates each person against their own history \u2014 never against a cohort average.",
      );

      // Step 3
      const step3Num = steps[2]?.querySelector(".welcome-step__number");
      const step3Title = steps[2]?.querySelector(".welcome-step__title");
      const step3Body = steps[2]?.querySelector(".welcome-step__body");
      expect(step3Num).toHaveTextContent("Step 3");
      expect(step3Title).toHaveTextContent("Review the cohort");
      expect(step3Body).toHaveTextContent(
        "Alphabetical and unranked. Click any person for their full assessment and manager briefing.",
      );

      // Link to /ingest
      const link = screen.getByRole("link", { name: /Get started/i });
      expect(link).toHaveAttribute("href", "/ingest");
    });

    it("has no automatically detectable accessibility violations", async () => {
      const { container } = renderWelcomeState("analyst");
      expect((await axe(container)).violations).toEqual([]);
    });
  });

  describe("manager role", () => {
    it("renders heading, subtext, and wellbeing note without pipeline steps", () => {
      const { container } = renderWelcomeState("manager");

      const heading = container.querySelector("h2.welcome-state__heading");
      expect(heading).toHaveTextContent("No briefings available yet");

      const text = container.querySelector("p.welcome-state__text");
      expect(text).toHaveTextContent(
        "Your wellbeing team will run the analysis. Once ready, you'll see supportive briefings for your team members here.",
      );

      const note = container.querySelector(".welcome-state__note");
      expect(note).toHaveTextContent(
        "This system is a wellbeing prompt, not a performance tool. Scores and diagnostics are not shown in this view.",
      );

      expect(container.querySelector(".welcome-steps")).toBeNull();
      expect(screen.queryByRole("link")).toBeNull();
    });

    it("has no automatically detectable accessibility violations", async () => {
      const { container } = renderWelcomeState("manager");
      expect((await axe(container)).violations).toEqual([]);
    });
  });

  describe("employee role", () => {
    it("renders heading, subtext, and privacy note without pipeline steps", () => {
      const { container } = renderWelcomeState("employee");

      const heading = container.querySelector("h2.welcome-state__heading");
      expect(heading).toHaveTextContent("Your wellbeing dashboard");

      const text = container.querySelector("p.welcome-state__text");
      expect(text).toHaveTextContent(
        "No self-assessment data is available yet. Once your team's wellbeing analysis is ready, your own trajectory will appear here.",
      );

      const note = container.querySelector(".welcome-state__note");
      expect(note).toHaveTextContent(
        "Only your own data is visible. Nobody else's assessments are shown.",
      );

      expect(container.querySelector(".welcome-steps")).toBeNull();
      expect(screen.queryByRole("link")).toBeNull();
    });

    it("has no automatically detectable accessibility violations", async () => {
      const { container } = renderWelcomeState("employee");
      expect((await axe(container)).violations).toEqual([]);
    });
  });
});
