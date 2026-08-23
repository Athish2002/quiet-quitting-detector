import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { JSDOM } from 'jsdom';

// Create a JSDOM environment before Vitest sets up its own jsdom (setupFiles runs early)
const { window } = new JSDOM('<!DOCTYPE html><html><body></body></html>');
(globalThis as any).window = window;
(globalThis as any).document = window.document;

// Ensure jsdom globals are available immediately (setupFiles runs before test files)
if (typeof window !== 'undefined') {
  (globalThis as any).window = window;
  (globalThis as any).document = window.document;
}

// Stub window.matchMedia
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

// Stub ResizeObserver
class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as any).ResizeObserver = ResizeObserver;

// Stub IntersectionObserver
class IntersectionObserver {
  constructor() {}
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as any).IntersectionObserver = IntersectionObserver;

// Load userEvent after globals are ready and expose globally for tests
(async () => {
  const { default: userEvent } = await import('@testing-library/user-event');
  (globalThis as any).userEvent = userEvent;
})();
