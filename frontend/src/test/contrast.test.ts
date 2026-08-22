// Colour contrast, asserted against the tokens as actually declared in
// styles.css -- in BOTH themes.
//
// This is the handoff's rule 8 ("every band colour clears 4.5:1 against its
// paired background") turned into something that fails a build. It exists
// because the failure mode it guards is silent: a classification chip that
// drops to 3.8:1 still looks fine to whoever changed it, still renders, still
// passes every other test, and is simply unreadable for a chunk of the people
// it describes. Nobody notices until someone cannot read their own band.
//
// Dark mode is the specific reason this is enforced rather than documented.
// The handoff specifies a light palette only and verifies those four pairs by
// hand; adding a second theme doubled the surface area and moved it out of the
// range anyone checks by eye. `design/verify_contrast.py` derives the values --
// this test is what stops them drifting afterwards.
//
// It parses the CSS as text on purpose. Vitest runs with `css: false`, so jsdom
// never resolves a custom property; asserting on the stylesheet itself is also
// the stricter check, because it fails if the TOKENS change, not merely if some
// component happens to render the wrong colour today.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// Vitest sets cwd to the config root, which is `frontend/`.
const CSS_PATH = resolve(process.cwd(), "src/styles.css");

// Comments are stripped before parsing: the explanatory blocks in styles.css
// contain braces and colons, and a naive scan otherwise reads them as tokens.
const CSS = readFileSync(CSS_PATH, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

/** WCAG 2.x floor for normal-size text. */
const TEXT_FLOOR = 4.5;

type Tokens = Readonly<Record<string, string>>;

function blockFor(selector: string): string {
  // `^` with the multiline flag keeps `.app-shell {` from also matching inside
  // `[data-theme="dark"] .app-shell {`, which contains the same substring.
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const body = new RegExp(`^${escaped}\\s*\\{([^}]*)\\}`, "m").exec(CSS)?.[1];
  if (body === undefined) {
    throw new Error(`No rule for selector "${selector}" in ${CSS_PATH}`);
  }
  return body;
}

function tokensFor(selector: string): Tokens {
  const tokens: Record<string, string> = {};
  for (const match of blockFor(selector).matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    const [, name, value] = match;
    if (name !== undefined && value !== undefined) {
      tokens[name] = value.trim();
    }
  }
  return tokens;
}

/** Look a token up by name, failing loudly rather than yielding NaN downstream. */
function get(tokens: Tokens, name: string): string {
  const value = tokens[name];
  if (value === undefined) {
    throw new Error(`Token ${name} is not declared`);
  }
  return value;
}

// --- WCAG relative luminance -------------------------------------------------

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const h = hex.replace("#", "");
  if (!/^[0-9a-f]{6}$/i.test(h)) {
    throw new Error(`Expected a 6-digit hex colour, got "${hex}"`);
  }
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(fg: string, bg: string): number {
  const a = luminance(fg);
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

// --- Themes ------------------------------------------------------------------

const light = tokensFor(".app-shell");
// The dark rule overrides only the colours, so the two are layered rather than
// swapped -- exactly how the cascade resolves them in the browser. Layering
// here also means a token added to light but forgotten in dark is still
// checked, against its light value, which is usually how that bug surfaces.
const dark: Tokens = { ...light, ...tokensFor('[data-theme="dark"] .app-shell') };

const BANDS = ["healthy", "watch", "at-risk", "exit"] as const;

const THEMES: ReadonlyArray<readonly [string, Tokens]> = [
  ["light", light],
  ["dark", dark],
];

describe.each(THEMES)("%s theme", (_themeName, t) => {
  describe("classification bands", () => {
    it.each(BANDS)("%s is readable on its own chip", (band) => {
      expect(contrast(get(t, `--${band}`), get(t, `--${band}-bg`))).toBeGreaterThanOrEqual(
        TEXT_FLOOR,
      );
    });

    // Trajectory bar labels and week markers put a band colour directly on the
    // page with no chip behind it. Clearing the chip is not enough on its own.
    it.each(BANDS)("%s is readable on the bare neutrals", (band) => {
      expect(contrast(get(t, `--${band}`), get(t, "--paper"))).toBeGreaterThanOrEqual(TEXT_FLOOR);
      expect(contrast(get(t, `--${band}`), get(t, "--surface"))).toBeGreaterThanOrEqual(TEXT_FLOOR);
    });

    // Rule 2: the bands mean "classification" and nothing else. If one is also
    // the accent, that meaning leaks onto every button and link on the page and
    // the colour stops carrying information.
    it.each(BANDS)("%s is not reused as the accent", (band) => {
      expect(get(t, `--${band}`).toLowerCase()).not.toBe(get(t, "--accent").toLowerCase());
    });
  });

  describe("text and accent", () => {
    it.each(["--ink", "--muted", "--accent"])("%s is readable on both grounds", (name) => {
      expect(contrast(get(t, name), get(t, "--paper"))).toBeGreaterThanOrEqual(TEXT_FLOOR);
      expect(contrast(get(t, name), get(t, "--surface"))).toBeGreaterThanOrEqual(TEXT_FLOOR);
    });

    it("is readable on the accent tint used for hover and selection", () => {
      expect(contrast(get(t, "--ink"), get(t, "--accent-bg"))).toBeGreaterThanOrEqual(TEXT_FLOOR);
      expect(contrast(get(t, "--accent"), get(t, "--accent-bg"))).toBeGreaterThanOrEqual(
        TEXT_FLOOR,
      );
    });

    // The primary button is a --surface-coloured label on an --accent fill, and
    // it has to stay legible through hover and active too.
    it.each(["--accent", "--accent-hover", "--accent-active"])(
      "primary button label is readable on %s",
      (fill) => {
        expect(contrast(get(t, "--surface"), get(t, fill))).toBeGreaterThanOrEqual(TEXT_FLOOR);
      },
    );
  });
});

describe("geometry", () => {
  // "Border radius: 0 everywhere. No exceptions." Asserted so that softening it
  // has to be a deliberate edit to this test rather than a quiet default.
  it("keeps the radius token at zero", () => {
    expect(get(light, "--radius")).toBe("0");
  });
});

describe("known-thin margins", () => {
  // Recomputed under WCAG 2.x, Healthy is 4.53:1 -- not the 4.59:1 the handoff
  // states. It passes, but with 0.03 to spare, which is far too little to
  // absorb a casual retune. This test names the number so anyone nudging the
  // green sees what the real headroom was before they touched it.
  it("documents how little room light-mode Healthy has", () => {
    const measured = contrast(get(light, "--healthy"), get(light, "--healthy-bg"));
    expect(measured).toBeGreaterThanOrEqual(TEXT_FLOOR);
    expect(measured).toBeLessThan(4.6);
  });
});
