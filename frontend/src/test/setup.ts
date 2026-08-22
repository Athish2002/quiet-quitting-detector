import "@testing-library/jest-dom/vitest";

// jsdom implements no `matchMedia`, and from S2 the app shell always renders
// ThemeToggle, which asks for the OS colour-scheme preference on first render.
// Without this every test that mounts the shell throws before it asserts
// anything. Reports "no preference" so tests start in light mode deterministically
// rather than inheriting whatever the machine running them prefers.
if (!window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
