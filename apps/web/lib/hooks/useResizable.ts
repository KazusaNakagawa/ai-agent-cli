"use client"
import { useCallback, useEffect, useState } from "react"

type Options = {
  /** localStorage key the width is persisted under. */
  storageKey: string
  defaultWidth: number
  minWidth: number
  maxWidth: number
  /**
   * Drag direction relative to the resized element:
   * - "right": handle on the element's right edge (default), drag right = wider
   * - "left":  handle on the element's left edge, drag left = wider
   */
  edge?: "right" | "left"
}

/**
 * Reusable horizontal panel resizing. Tracks a pixel width in React state,
 * restores it from localStorage on mount, and persists it when a drag ends.
 *
 * Returns the current `width` (apply via `style={{ width }}`) and a
 * `startResize` pointer-down handler to wire onto a drag handle.
 */
export function useResizable({
  storageKey,
  defaultWidth,
  minWidth,
  maxWidth,
  edge = "right",
}: Options) {
  const [width, setWidth] = useState(defaultWidth)

  // Restore persisted width on mount (client-only to avoid SSR mismatch).
  useEffect(() => {
    const saved = Number(localStorage.getItem(storageKey))
    if (saved >= minWidth && saved <= maxWidth) setWidth(saved)
  }, [storageKey, minWidth, maxWidth])

  const startResize = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault()
      const startX = e.clientX
      const startWidth = width
      const dir = edge === "left" ? -1 : 1
      const clamp = (w: number) => Math.min(maxWidth, Math.max(minWidth, w))

      // AbortController removes every listener in one call, so a drag ended by
      // pointercancel (OS gesture, context menu) can't leak listeners.
      const controller = new AbortController()
      const { signal } = controller
      let next = startWidth

      const onMove = (ev: PointerEvent) => {
        next = clamp(startWidth + dir * (ev.clientX - startX))
        setWidth(next)
      }
      const onEnd = () => {
        controller.abort()
        try {
          localStorage.setItem(storageKey, String(next))
        } catch {
          // localStorage unavailable (private mode / quota); width still applies
        }
      }
      window.addEventListener("pointermove", onMove, { signal })
      window.addEventListener("pointerup", onEnd, { signal })
      window.addEventListener("pointercancel", onEnd, { signal })
    },
    [width, storageKey, minWidth, maxWidth, edge],
  )

  return { width, startResize }
}
