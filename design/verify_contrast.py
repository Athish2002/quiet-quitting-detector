"""Verify every colour pair in the redesign clears its WCAG floor, in both themes.

The design handoff (design/design_handoff_qq_ui/README.md, rule 8) requires every
classification band to clear 4.5:1 against its paired background. The handoff verifies
LIGHT only. Dark mode is our addition, so the dark set is derived and verified here.

Run:  python design/verify_contrast.py
Exits non-zero if anything fails, so it can be wired into CI.

This is the reference implementation. `frontend/src/test/contrast.test.ts` (session 1)
asserts the same floors against the tokens as actually declared in styles.css -- that
test is the one that catches drift; this script is for deriving and re-checking values.
"""

from __future__ import annotations

import sys

# --- WCAG 2.x relative luminance -------------------------------------------------


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def ratio(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# --- Palette ---------------------------------------------------------------------

LIGHT = {
    "paper": "#F2F5F4",
    "surface": "#FFFFFF",
    "ink": "#1B2422",
    "muted": "#5A6A66",
    "rule": "#D2DAD7",
    "accent": "#1D4E6B",
    "accent_bg": "#EAF1F5",
}

DARK = {
    "paper": "#121817",
    "surface": "#1B2422",
    "ink": "#F2F5F4",
    "muted": "#9DACA8",
    "rule": "#323E3B",
    "accent": "#7FB6D6",
    "accent_bg": "#1A2C38",
}

# Classification bands: (name, foreground, chip background)
BANDS_LIGHT = [
    ("Healthy", "#47795A", "#EDF4EF"),
    ("Watch", "#8A6A22", "#FAF4E6"),
    ("At Risk", "#9E5333", "#FAEFEA"),
    ("Silent Exit", "#7E3A2C", "#F9EDEA"),
]

BANDS_DARK = [
    ("Healthy", "#44A769", "#152119"),
    ("Watch", "#B19148", "#211D15"),
    ("At Risk", "#C18267", "#211815"),
    ("Silent Exit", "#C58072", "#211715"),
]

TEXT_FLOOR = 4.5  # WCAG AA, normal text
failures: list[str] = []


def check(label: str, fg: str, bg: str, floor: float) -> None:
    r = ratio(fg, bg)
    ok = r >= floor
    if not ok:
        failures.append(f"{label}: {fg} on {bg} = {r:.2f}:1 (needs {floor})")
    print(f"  {'PASS' if ok else 'FAIL'}  {label:44} {r:5.2f}:1  (floor {floor})")


def check_theme(
    name: str, tokens: dict[str, str], bands: list[tuple[str, str, str]]
) -> None:
    print(f"\n=== {name} ===")
    paper, surface = tokens["paper"], tokens["surface"]

    print("-- classification bands on their own chip --")
    for band, fg, bg in bands:
        check(f"{band} on its chip", fg, bg, TEXT_FLOOR)

    # A band-coloured trajectory label sits directly on a neutral, not on a chip,
    # so it has to clear the floor there too.
    print("-- the same band colours on the bare neutrals --")
    for band, fg, _ in bands:
        check(f"{band} on paper", fg, paper, TEXT_FLOOR)
        check(f"{band} on surface", fg, surface, TEXT_FLOOR)

    print("-- neutrals and accent --")
    check("ink on paper", tokens["ink"], paper, TEXT_FLOOR)
    check("ink on surface", tokens["ink"], surface, TEXT_FLOOR)
    check("muted on paper", tokens["muted"], paper, TEXT_FLOOR)
    check("muted on surface", tokens["muted"], surface, TEXT_FLOOR)
    check("accent on paper", tokens["accent"], paper, TEXT_FLOOR)
    check("accent on surface", tokens["accent"], surface, TEXT_FLOOR)
    check("ink on accent-bg", tokens["ink"], tokens["accent_bg"], TEXT_FLOOR)
    check("accent on accent-bg", tokens["accent"], tokens["accent_bg"], TEXT_FLOOR)
    # Primary button: surface-coloured text on an accent fill.
    check("surface on accent (primary btn)", surface, tokens["accent"], TEXT_FLOOR)

    # Rules are decorative hairlines, not UI boundaries -- the light design ships them
    # at 1.30:1, so holding dark to 3:1 would make dark-mode rules visibly heavier than
    # the design intends. Reported, not asserted.
    print("-- rules (reported, not asserted: light ships at 1.30:1) --")
    print(f"        rule on paper   {ratio(tokens['rule'], paper):5.2f}:1")
    print(f"        rule on surface {ratio(tokens['rule'], surface):5.2f}:1")


if __name__ == "__main__":
    check_theme("LIGHT", LIGHT, BANDS_LIGHT)
    check_theme("DARK", DARK, BANDS_DARK)

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All pairs clear their floor, in both themes.")
