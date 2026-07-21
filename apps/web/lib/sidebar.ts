// Single source of truth for the sidebar collapse persistence keys.
// Referenced by:
//   - components/Sidebar.tsx (state ↔ DOM sync)
//   - components/ThemeProvider.tsx (themeBootScript, written into the inline
//     pre-hydration script via JSON.stringify so a rename here propagates
//     without manually touching the script)
//   - tests/sidebar.test.tsx
export const SIDEBAR_COLLAPSED_KEY = "ai-agent:sidebar-collapsed"
export const SIDEBAR_COLLAPSED_ATTR = "data-sidebar-collapsed"

// Resizable rail width. The width lives in a CSS custom property on <html>
// so the pre-hydration boot script can restore it before first paint (same
// pattern as the collapsed attribute), avoiding a flash from the CSS default.
export const SIDEBAR_WIDTH_KEY = "ai-agent:sidebar-width"
export const SIDEBAR_WIDTH_VAR = "--sidebar-width"
export const SIDEBAR_MIN_WIDTH = 180
export const SIDEBAR_MAX_WIDTH = 480
export const SIDEBAR_DEFAULT_WIDTH = 240 // matches the 15rem CSS default
