// Single source of truth for the sidebar collapse persistence keys.
// Referenced by:
//   - components/Sidebar.tsx (state ↔ DOM sync)
//   - components/ThemeProvider.tsx (themeBootScript, written into the inline
//     pre-hydration script via JSON.stringify so a rename here propagates
//     without manually touching the script)
//   - tests/sidebar.test.tsx
export const SIDEBAR_COLLAPSED_KEY = "ai-agent:sidebar-collapsed"
export const SIDEBAR_COLLAPSED_ATTR = "data-sidebar-collapsed"
