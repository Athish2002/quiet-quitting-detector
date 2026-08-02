/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api to the FastAPI backend so the browser makes
// same-origin requests. That matters for more than convenience: the Phase 4
// CSP sets `connect-src 'self'`, and a frontend calling a different origin in
// development would work locally and fail the moment it was served for real.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Vitest owns src/, Playwright owns e2e/. Without this split vitest picks
    // up the Playwright specs, fails to resolve @playwright/test's runner, and
    // reports a failure that has nothing to do with the code under test --
    // noise that trains people to ignore a red suite.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["node_modules", "dist", "e2e"],
  },
});
