# Header Service Switcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the web UI into two services (Briefing, Journal) selectable via a header tab bar; the sidebar shows only the active service's items, with the active service derived from the current route.

**Architecture:** A single `lib/services.ts` defines the `SERVICES` model and `serviceForPath(pathname)`. `ServiceTabs` (header) and `Sidebar` both derive everything from the route via that function — the route is the only state. The `(main)` layout renders `ServiceTabs` above the page content.

**Tech Stack:** Next.js 14 App Router, TypeScript, React, Vitest + @testing-library/react.

## Global Constraints

- Working dir: `/Users/nakagawakazusa/work/ai-agent`
- Branch: `feat/issue-313-service-switcher` (already checked out)
- Test runner: `cd apps/web && npx vitest run` — all tests must stay green
- Path alias `@/` maps to `apps/web/`
- Frontend test files: `apps/web/tests/**/*.test.{ts,tsx}`
- Briefing service (`defaultHref: /portfolio`): Portfolio, Watch Sectors, Geopolitical Risks, Run, Q&A Chat, Briefing
- Journal service (`defaultHref: /journal`): Journal
- Config / Settings stays global (sidebar bottom, unchanged)
- `serviceForPath` matching: a service owns `pathname` if any `item.href === pathname` or `pathname.startsWith(item.href + "/")`; first match in `SERVICES` order wins; no match → `SERVICES[0]` (briefing)
- Code comments in English
- Conventional commits format

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `apps/web/lib/services.ts` | `SERVICES` model + `serviceForPath()` — single source of truth |
| Create | `apps/web/tests/services.test.ts` | Unit tests for `serviceForPath` |
| Create | `apps/web/components/ServiceTabs.tsx` | Header tab bar; active tab from route |
| Create | `apps/web/tests/service-tabs.test.tsx` | ServiceTabs tests |
| Modify | `apps/web/components/Sidebar.tsx` | Render active service's items instead of flat `ITEMS` |
| Modify | `apps/web/tests/sidebar.test.tsx` | Make `usePathname` mock mutable; add per-service item tests |
| Modify | `apps/web/app/(main)/layout.tsx` | Render `<ServiceTabs />` atop main content |

---

## Task 1: `services.ts` — service model + `serviceForPath`

**Files:**
- Create: `apps/web/lib/services.ts`
- Create: `apps/web/tests/services.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export type ServiceId = "briefing" | "journal"
  export type NavItem = { href: string; label: string; icon: string }
  export type Service = { id: ServiceId; label: string; defaultHref: string; items: NavItem[] }
  export const SERVICES: Service[]
  export function serviceForPath(pathname: string): Service
  ```

- [ ] **Step 1: Write the failing test**

```ts
// apps/web/tests/services.test.ts
import { describe, expect, it } from "vitest"
import { SERVICES, serviceForPath } from "@/lib/services"

describe("SERVICES", () => {
  it("defines briefing first (fallback) and journal", () => {
    expect(SERVICES.map((s) => s.id)).toEqual(["briefing", "journal"])
    expect(SERVICES[0].defaultHref).toBe("/portfolio")
    expect(SERVICES[1].defaultHref).toBe("/journal")
  })

  it("briefing owns its six items, journal owns one", () => {
    const briefing = SERVICES.find((s) => s.id === "briefing")!
    expect(briefing.items.map((i) => i.href)).toEqual([
      "/portfolio", "/watch-sectors", "/geopolitical", "/run", "/chat", "/briefing",
    ])
    const journal = SERVICES.find((s) => s.id === "journal")!
    expect(journal.items.map((i) => i.href)).toEqual(["/journal"])
  })
})

describe("serviceForPath", () => {
  it.each([
    ["/portfolio", "briefing"],
    ["/watch-sectors", "briefing"],
    ["/geopolitical", "briefing"],
    ["/run", "briefing"],
    ["/chat", "briefing"],
    ["/briefing", "briefing"],
    ["/journal", "journal"],
  ])("maps %s to %s", (pathname, expected) => {
    expect(serviceForPath(pathname).id).toBe(expected)
  })

  it("matches nested routes by prefix", () => {
    expect(serviceForPath("/journal/2026-06-27").id).toBe("journal")
    expect(serviceForPath("/briefing/some-file.md").id).toBe("briefing")
  })

  it("falls back to briefing for unknown routes", () => {
    expect(serviceForPath("/config/usage").id).toBe("briefing")
    expect(serviceForPath("/auth").id).toBe("briefing")
    expect(serviceForPath("/totally-unknown").id).toBe("briefing")
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd apps/web && npx vitest run tests/services.test.ts
```

Expected: FAIL — "Cannot find module '@/lib/services'"

- [ ] **Step 3: Implement `services.ts`**

```ts
// apps/web/lib/services.ts
export type ServiceId = "briefing" | "journal"

export type NavItem = { href: string; label: string; icon: string }

export type Service = {
  id: ServiceId
  label: string
  defaultHref: string
  items: NavItem[]
}

// Single source of truth for the service model. Order matters: the first entry
// is the fallback when a route belongs to no service (Config / auth are global).
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

// Derive the active service from the current route. A service owns the path if
// any of its item hrefs matches exactly or is a path-segment prefix. First
// match wins; unmatched routes fall back to the first service (briefing).
export function serviceForPath(pathname: string): Service {
  for (const service of SERVICES) {
    for (const item of service.items) {
      if (pathname === item.href || pathname.startsWith(item.href + "/")) {
        return service
      }
    }
  }
  return SERVICES[0]
}
```

- [ ] **Step 4: Run to verify pass**

```bash
cd apps/web && npx vitest run tests/services.test.ts
```

Expected: PASS (all cases)

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/services.ts apps/web/tests/services.test.ts
git commit -m "feat(web): add service model and serviceForPath"
```

---

## Task 2: `ServiceTabs` header component

**Files:**
- Create: `apps/web/components/ServiceTabs.tsx`
- Create: `apps/web/tests/service-tabs.test.tsx`

**Interfaces:**
- Consumes: `SERVICES`, `serviceForPath` from `@/lib/services` (Task 1)
- Produces: `export function ServiceTabs(): JSX.Element`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/tests/service-tabs.test.tsx
import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ServiceTabs } from "@/components/ServiceTabs"

// Mutable pathname so each test can place itself on a different route.
let mockPathname = "/portfolio"
vi.mock("next/navigation", () => ({ usePathname: () => mockPathname }))
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: any) => (
    <a href={href} {...rest}>{children}</a>
  ),
}))

afterEach(() => { mockPathname = "/portfolio" })

describe("ServiceTabs", () => {
  it("renders one tab per service linking to its defaultHref", () => {
    render(<ServiceTabs />)
    const briefing = screen.getByTestId("service-tab-briefing")
    const journal = screen.getByTestId("service-tab-journal")
    expect(briefing).toHaveAttribute("href", "/portfolio")
    expect(journal).toHaveAttribute("href", "/journal")
  })

  it("marks the briefing tab active on a briefing route", () => {
    mockPathname = "/chat"
    render(<ServiceTabs />)
    expect(screen.getByTestId("service-tab-briefing")).toHaveAttribute("aria-current", "page")
    expect(screen.getByTestId("service-tab-journal")).not.toHaveAttribute("aria-current")
  })

  it("marks the journal tab active on a journal route", () => {
    mockPathname = "/journal"
    render(<ServiceTabs />)
    expect(screen.getByTestId("service-tab-journal")).toHaveAttribute("aria-current", "page")
    expect(screen.getByTestId("service-tab-briefing")).not.toHaveAttribute("aria-current")
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd apps/web && npx vitest run tests/service-tabs.test.tsx
```

Expected: FAIL — "Cannot find module '@/components/ServiceTabs'"

- [ ] **Step 3: Implement `ServiceTabs.tsx`**

```tsx
// apps/web/components/ServiceTabs.tsx
"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"

import { SERVICES, serviceForPath } from "@/lib/services"
import { cn } from "@/lib/utils"

export function ServiceTabs() {
  const pathname = usePathname()
  const activeId = serviceForPath(pathname).id

  return (
    <nav
      data-testid="service-tabs"
      aria-label="Services"
      className="flex items-center gap-1 border-b px-8 py-2"
    >
      {SERVICES.map((service) => {
        const active = service.id === activeId
        return (
          <Link
            key={service.id}
            href={service.defaultHref}
            data-testid={`service-tab-${service.id}`}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              active
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/50",
            )}
          >
            {service.label}
          </Link>
        )
      })}
    </nav>
  )
}
```

- [ ] **Step 4: Run to verify pass**

```bash
cd apps/web && npx vitest run tests/service-tabs.test.tsx
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/ServiceTabs.tsx apps/web/tests/service-tabs.test.tsx
git commit -m "feat(web): add ServiceTabs header component"
```

---

## Task 3: Sidebar renders active service's items

**Files:**
- Modify: `apps/web/components/Sidebar.tsx`
- Modify: `apps/web/tests/sidebar.test.tsx`

**Interfaces:**
- Consumes: `serviceForPath` from `@/lib/services` (Task 1)

The current `Sidebar.tsx` has a module-level `const ITEMS: Item[] = [...]` (lines ~20-30)
and renders `{ITEMS.map(...)}` inside the component. Replace the data source with the
active service's items, derived from `pathname` (already available via `usePathname()`).

- [ ] **Step 1: Make the existing `usePathname` mock mutable + add per-service tests**

In `apps/web/tests/sidebar.test.tsx`, replace the static mock:

```tsx
vi.mock("next/navigation", () => ({
  usePathname: () => "/portfolio",
}))
```

with a mutable one:

```tsx
let mockPathname = "/portfolio"
vi.mock("next/navigation", () => ({ usePathname: () => mockPathname }))
```

Add a `beforeEach(() => { mockPathname = "/portfolio" })` inside the top-level area (or
within each existing `describe`'s `beforeEach`, append the reset). Then add a new
describe block at the end of the file:

```tsx
describe("Sidebar service items", () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute(HTML_ATTR)
    mockPathname = "/portfolio"
  })

  it("shows the six Briefing items on a briefing route", () => {
    mockPathname = "/portfolio"
    renderSidebar()
    expect(screen.getByTestId("nav-portfolio")).toBeInTheDocument()
    expect(screen.getByTestId("nav-chat")).toBeInTheDocument()
    expect(screen.getByTestId("nav-briefing")).toBeInTheDocument()
    expect(screen.queryByTestId("nav-journal")).not.toBeInTheDocument()
  })

  it("shows only the Journal item on a journal route", () => {
    mockPathname = "/journal"
    renderSidebar()
    expect(screen.getByTestId("nav-journal")).toBeInTheDocument()
    expect(screen.queryByTestId("nav-portfolio")).not.toBeInTheDocument()
  })
})
```

Note: the existing `nav-<href>` testid is `nav-` + `item.href.slice(1)`, so
`/chat` → `nav-chat`, `/journal` → `nav-journal`.

- [ ] **Step 2: Run to verify the new tests fail**

```bash
cd apps/web && npx vitest run tests/sidebar.test.tsx
```

Expected: FAIL — the journal-route test still shows `nav-portfolio` because the
sidebar renders the flat `ITEMS` list regardless of route.

- [ ] **Step 3: Update `Sidebar.tsx` to use the active service's items**

Remove the module-level `ITEMS` constant and its `Item` type (lines ~20-30):

```ts
type Item = { href: string; label: string; icon: string }

const ITEMS: Item[] = [
  { href: "/portfolio", label: "Portfolio", icon: "📊" },
  { href: "/watch-sectors", label: "Watch Sectors", icon: "🌐" },
  { href: "/geopolitical", label: "Geopolitical Risks", icon: "🗺️" },
  { href: "/run", label: "Run", icon: "▶️" },
  { href: "/chat", label: "Q&A Chat", icon: "💬" },
  { href: "/journal", label: "Journal", icon: "📓" },
  { href: "/briefing", label: "Briefing", icon: "📚" },
]
```

Add the import near the other `@/lib` imports at the top:

```ts
import { serviceForPath } from "@/lib/services"
```

Inside the component, just after `const pathname = usePathname()`, derive the items:

```ts
const items = serviceForPath(pathname).items
```

Change the render loop from `{ITEMS.map((item) => {` to `{items.map((item) => {`.
Leave the rest of the row rendering (active check, run dot, testids) unchanged.

- [ ] **Step 4: Run to verify pass**

```bash
cd apps/web && npx vitest run tests/sidebar.test.tsx
```

Expected: PASS (existing collapse/resize/config tests + the two new ones)

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/Sidebar.tsx apps/web/tests/sidebar.test.tsx
git commit -m "feat(web): sidebar renders only the active service's items"
```

---

## Task 4: Render `ServiceTabs` in the main layout

**Files:**
- Modify: `apps/web/app/(main)/layout.tsx`

**Interfaces:**
- Consumes: `ServiceTabs` from `@/components/ServiceTabs` (Task 2)

The current layout renders:

```tsx
<div className="flex h-dvh overflow-hidden">
  <Sidebar />
  <main className="flex-1 overflow-y-auto p-8">{children}</main>
</div>
```

- [ ] **Step 1: Add the import**

At the top of `apps/web/app/(main)/layout.tsx`, with the other component imports:

```ts
import { ServiceTabs } from "@/components/ServiceTabs"
```

- [ ] **Step 2: Render `ServiceTabs` above the page content**

Replace the `<main>` block with:

```tsx
<main className="flex flex-1 flex-col overflow-hidden">
  <ServiceTabs />
  <div className="flex-1 overflow-y-auto p-8">{children}</div>
</main>
```

(The scroll + padding move to the inner wrapper so the tab bar stays fixed at
the top of the content column and spans full width.)

- [ ] **Step 3: Run the full suite**

```bash
cd apps/web && npx vitest run
```

Expected: all tests PASS

- [ ] **Step 4: Build check (catches App Router server/client boundary issues)**

```bash
cd apps/web && npx tsc --noEmit
```

Expected: no type errors

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/(main)/layout.tsx
git commit -m "feat(web): render ServiceTabs atop the main content"
```

---

## Task 5: Manual verification + PR

- [ ] **Step 1: Run the dev server**

```bash
cd apps/web && npm run dev
```

- [ ] **Step 2: Verify behaviour**

1. Load `/portfolio` → header shows **Briefing** (active) and **Journal** tabs; sidebar shows the 6 Briefing items.
2. Click **Journal** → navigates to `/journal`; sidebar shows only Journal; Journal tab is active.
3. Click **Briefing** → navigates to `/portfolio`; sidebar shows the 6 Briefing items again.
4. Navigate to `/briefing` directly → Briefing tab active, 6 items.
5. Open Config (settings modal) → still available from the sidebar bottom in both services.

- [ ] **Step 3: Push and open PR**

```bash
git push -u origin feat/issue-313-service-switcher
gh pr create --base dev \
  --title "feat(web): add header service switcher (Briefing / Journal)" \
  --body "$(cat <<'EOF'
## Summary

- Add a `services.ts` model + `serviceForPath()` deriving the active service from the route
- New `ServiceTabs` header bar switches between Briefing and Journal
- Sidebar now renders only the active service's items; Config stays global
- Sets up adding a new service later as a one-entry change to `SERVICES`

## Test plan

- [ ] `cd apps/web && npx vitest run` — all pass
- [ ] Briefing tab → /portfolio, sidebar shows 6 items
- [ ] Journal tab → /journal, sidebar shows only Journal
- [ ] Direct nav to /briefing keeps Briefing active
- [ ] Config reachable from both services

Closes #313
EOF
)"
```
