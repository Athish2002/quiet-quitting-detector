// frontend/src/components/BrandSymbol.test.tsx

import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";
import { BrandSymbol } from "./BrandSymbol";

describe("BrandSymbol", () => {
  it("renders the SVG emblem with accessible role and label", () => {
    render(<BrandSymbol label="Quiet-Quitting Detector Symbol" />);

    const symbol = screen.getByRole("img", { name: "Quiet-Quitting Detector Symbol" });
    expect(symbol).toBeInTheDocument();
  });

  it("applies sizing correctly", () => {
    const { rerender } = render(<BrandSymbol size="sm" />);
    expect(screen.getByRole("img")).toHaveStyle({ width: "24px", height: "24px" });

    rerender(<BrandSymbol size="lg" />);
    expect(screen.getByRole("img")).toHaveStyle({ width: "48px", height: "48px" });

    rerender(<BrandSymbol size={60} />);
    expect(screen.getByRole("img")).toHaveStyle({ width: "60px", height: "60px" });
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = render(<BrandSymbol />);
    expect((await axe(container)).violations).toEqual([]);
  });
});
