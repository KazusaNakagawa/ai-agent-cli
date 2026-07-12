import "@testing-library/jest-dom/vitest"

// jsdom doesn't implement ResizeObserver. react-zoom-pan-pinch (used by
// MermaidModal) requires it to compute initial centering, so stub it out
// for tests.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}
