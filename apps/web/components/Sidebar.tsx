"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useCallback, useEffect, useState } from "react"

import { JournalSidebarList } from "@/components/journal/JournalSidebarList"
import { ResizeHandle } from "@/components/ResizeHandle"
import { SettingsModal } from "@/components/settings/SettingsModal"
import { useJobState } from "@/lib/jobStore"
import {
  SIDEBAR_COLLAPSED_ATTR,
  SIDEBAR_COLLAPSED_KEY,
  SIDEBAR_DEFAULT_WIDTH,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  SIDEBAR_WIDTH_KEY,
  SIDEBAR_WIDTH_VAR,
} from "@/lib/sidebar"
import { serviceForPath } from "@/lib/services"
import { cn } from "@/lib/utils"

export function Sidebar() {
  const pathname = usePathname()
  const items = serviceForPath(pathname).items
  const onJournal = pathname === "/journal" || pathname.startsWith("/journal/")
  const { isBackgrounded: runJobActive } = useJobState()
  // Initialize to false so SSR and the first client render agree (avoiding
  // a hydration mismatch on data-collapsed / aria-expanded / title). The
  // visible width is already correct on first paint because CSS reacts to
  // the html attribute the pre-hydration script writes; the React state
  // catches up in the mount effect below.
  const [collapsed, setCollapsed] = useState(false)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    setCollapsed(
      document.documentElement.getAttribute(SIDEBAR_COLLAPSED_ATTR) === "true",
    )
    setHydrated(true)
  }, [])

  // Persist + mirror to the html attribute whenever the user toggles. Skip
  // the initial mount tick so we don't write back the value we just read.
  useEffect(() => {
    if (!hydrated) return
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed))
    } catch {
      // localStorage unavailable (private mode / quota); state still works
    }
    if (collapsed) {
      document.documentElement.setAttribute(SIDEBAR_COLLAPSED_ATTR, "true")
    } else {
      document.documentElement.removeAttribute(SIDEBAR_COLLAPSED_ATTR)
    }
  }, [collapsed, hydrated])

  const toggle = () => setCollapsed((prev) => !prev)

  // Drag the right edge to resize the rail. Width is written live to the
  // CSS custom property on <html> (the same one the boot script restores)
  // and persisted to localStorage on release.
  const onResizeStart = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault()
      const startX = e.clientX
      const root = document.documentElement
      const startWidth =
        parseInt(getComputedStyle(root).getPropertyValue(SIDEBAR_WIDTH_VAR), 10) ||
        root.querySelector<HTMLElement>("[data-sidebar-rail]")?.offsetWidth ||
        SIDEBAR_DEFAULT_WIDTH
      const clamp = (w: number) =>
        Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, w))

      const controller = new AbortController()
      const { signal } = controller

      const onMove = (ev: PointerEvent) => {
        const w = clamp(startWidth + (ev.clientX - startX))
        root.style.setProperty(SIDEBAR_WIDTH_VAR, `${w}px`)
      }
      // pointerup / pointercancel both end the drag so a cancelled gesture
      // (OS gesture, context menu) doesn't leak listeners. AbortController
      // removes every listener in one call.
      const onEnd = () => {
        controller.abort()
        const w = parseInt(
          getComputedStyle(root).getPropertyValue(SIDEBAR_WIDTH_VAR),
          10,
        )
        try {
          if (w) localStorage.setItem(SIDEBAR_WIDTH_KEY, String(w))
        } catch {
          // localStorage unavailable (private mode / quota); width still applies
        }
      }
      window.addEventListener("pointermove", onMove, { signal })
      window.addEventListener("pointerup", onEnd, { signal })
      window.addEventListener("pointercancel", onEnd, { signal })
    },
    [],
  )

  return (
    <aside
      data-sidebar-rail
      data-testid="sidebar"
      data-collapsed={collapsed}
      className="relative flex shrink-0 flex-col gap-4 overflow-hidden border-r bg-card p-4"
    >
      <div data-sidebar-header className="flex shrink-0 items-center justify-between">
        <span data-sidebar-brand className="px-2 text-base font-semibold">
          ai-agent
        </span>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          data-testid="sidebar-toggle"
          className="rounded-md p-1 text-sm text-muted-foreground transition-colors hover:bg-accent/50"
        >
          <span aria-hidden data-sidebar-toggle-icon />
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
      <section className="flex shrink-0 flex-col gap-1">
        <nav className="flex flex-col gap-1">
          {items.map((item) => {
            const active = pathname === item.href
            const showRunDot = item.href === "/run" && runJobActive
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                aria-label={item.label}
                data-sidebar-row
                data-testid={`nav-${item.href.slice(1)}`}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-accent font-medium text-accent-foreground"
                    : "hover:bg-accent/50",
                )}
              >
                <span aria-hidden>{item.icon}</span>
                <span data-sidebar-label>{item.label}</span>
                {showRunDot && (
                  <span
                    data-testid="sidebar-run-dot"
                    aria-label="Background job in progress"
                    className="ml-auto h-2 w-2 shrink-0 rounded-full bg-primary"
                  />
                )}
              </Link>
            )
          })}
        </nav>
      </section>

      {onJournal && !collapsed && <JournalSidebarList />}

      <section
        data-sidebar-section="config"
        className="flex shrink-0 flex-col gap-1"
      >
        <SettingsModal />
      </section>
      </div>
      {/* Right-edge drag handle to resize the rail (hidden when collapsed). */}
      {!collapsed && (
        <ResizeHandle
          onPointerDown={onResizeStart}
          ariaLabel="Resize sidebar"
          data-testid="sidebar-resizer"
        />
      )}
    </aside>
  )
}
