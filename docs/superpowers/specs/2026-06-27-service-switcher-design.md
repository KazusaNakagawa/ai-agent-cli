# Header Service Switcher Design

**Date:** 2026-06-27
**Status:** Approved

## Goal

Introduce a "service" concept to the web UI. The existing screens are split into
two services — **Briefing** and **Journal** — and a header tab bar switches
between them. The sidebar shows only the items belonging to the active service.
This sets up the structure for adding a third (new) service later as a small,
data-driven change.

## Background

Today the sidebar (`apps/web/components/Sidebar.tsx`) renders a single flat
`ITEMS` list (Portfolio, Watch Sectors, Geopolitical Risks, Run, Q&A Chat,
Journal, Briefing) and Config lives at the bottom via `SettingsModal`. There is
no header bar. Briefing and Journal are conceptually separate products sharing
one nav.

## Service → Screen Mapping

| Service | `defaultHref` | Sidebar items |
|---|---|---|
| **Briefing** | `/portfolio` | Portfolio, Watch Sectors, Geopolitical Risks, Run, Q&A Chat, Briefing |
| **Journal** | `/journal` | Journal |

- **Config / Settings** stays global — rendered for every service via the
  existing `SettingsModal` at the sidebar bottom. Not part of any service.
- Q&A Chat belongs to Briefing (its context is "today's briefing"). Journal has
  its own Brainstorm chat already.

## Architecture

Approach: **derive the active service from the route**. The route is the single
source of truth; there is no separate persisted/Context service state to keep in
sync. This avoids hydration and desync bugs and matches the existing
`usePathname()`-based active-link logic.

```
pathname ──serviceForPath()──▶ Service
                                 ├─▶ ServiceTabs: highlight active tab
                                 └─▶ Sidebar: render service.items only
```

## Components & Files

### New: `apps/web/lib/services.ts`

Single source of truth for the service model.

```ts
export type ServiceId = "briefing" | "journal"
export type NavItem = { href: string; label: string; icon: string }
export type Service = {
  id: ServiceId
  label: string
  defaultHref: string
  items: NavItem[]
}

export const SERVICES: Service[] = [
  {
    id: "briefing",
    label: "Briefing",
    defaultHref: "/portfolio",
    items: [
      { href: "/portfolio", label: "Portfolio", icon: "📊" },
      { href: "/watch-sectors", label: "Watch Sectors", icon: "🌐" },
      { href: "/geopolitical", label: "Geopolitical Risks", icon: "🗺️" },
      { href: "/run", label: "Run", icon: "▶️" },
      { href: "/chat", label: "Q&A Chat", icon: "💬" },
      { href: "/briefing", label: "Briefing", icon: "📚" },
    ],
  },
  {
    id: "journal",
    label: "Journal",
    defaultHref: "/journal",
    items: [{ href: "/journal", label: "Journal", icon: "📓" }],
  },
]

// Match by item href (exact or path prefix). Routes not owned by any service
// (e.g. /config/*, /auth) fall back to the first service (briefing) — Config is
// global so this has no user-visible effect.
export function serviceForPath(pathname: string): Service
```

`serviceForPath` matching rule: a service owns `pathname` if any `item.href`
equals `pathname` or is a prefix (`pathname === href || pathname.startsWith(href + "/")`).
First match wins in `SERVICES` order; no match → `SERVICES[0]` (briefing).

### New: `apps/web/components/ServiceTabs.tsx` (`"use client"`)

Horizontal tab bar rendered at the top of the main content area. Maps over
`SERVICES`; each tab is a `next/link` to `service.defaultHref`. Active tab =
`serviceForPath(usePathname()).id`. Active tab gets a distinct style
(`aria-current="page"`).

- `data-testid="service-tabs"` on the container
- `data-testid="service-tab-<id>"` on each tab
- Each tab exposes `aria-current` only when active

### Modify: `apps/web/components/Sidebar.tsx`

Replace the module-level flat `ITEMS` with the active service's items:

```ts
const items = serviceForPath(pathname).items
```

Everything else (collapse, resize, run dot, SettingsModal section) is unchanged.
The run dot still keys off `item.href === "/run"`.

### Modify: `apps/web/app/(main)/layout.tsx`

Render `<ServiceTabs />` above `{children}` inside `<main>`:

```tsx
<main className="flex-1 overflow-y-auto">
  <ServiceTabs />
  <div className="p-8">{children}</div>
</main>
```

(Padding moves to an inner wrapper so the tab bar can span full width with its
own padding, matching the mockup.)

## Behaviour

- Click **Journal** tab → navigate to `/journal`; sidebar shows only Journal.
- Click **Briefing** tab → navigate to `/portfolio`; sidebar shows the 6
  Briefing items.
- Landing on any Briefing-owned route (e.g. `/briefing`) → Briefing tab active,
  6 items in sidebar.
- `/config/*`, `/auth` (global settings, reached via SettingsModal) → briefing
  is the active service; no user-visible issue since Config is global.

## Error / Edge Handling

| Case | Behaviour |
|---|---|
| Route not in any service | `serviceForPath` returns `SERVICES[0]` (briefing) |
| Trailing slash / nested path | Prefix match (`startsWith(href + "/")`) handles nested routes |
| Adding a 3rd service later | Append one entry to `SERVICES`; tabs + sidebar update automatically |

## Testing

- **`services.ts`** (`tests/services.test.ts`): `serviceForPath` returns briefing
  for each Briefing route and for an unknown route; returns journal for
  `/journal`; prefix match works for a nested path.
- **`ServiceTabs`** (`tests/service-tabs.test.tsx`): renders one tab per service;
  the tab matching the mocked `usePathname` has `aria-current="page"` and the
  other does not; each tab links to its `defaultHref`.
- **`Sidebar`** (extend `tests/sidebar.test.tsx`): on `/journal` only the Journal
  nav row renders (Portfolio absent); on `/portfolio` the 6 Briefing rows render
  (Journal absent). Existing collapse/resize/config tests stay green.

## Out of Scope

- The actual third/new service (separate issue).
- Persisting "last visited page per service" (always land on `defaultHref`).
- Moving Config out of the sidebar.
- Per-service theming or icons in the header beyond label text.
