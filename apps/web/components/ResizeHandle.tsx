"use client"
import { cn } from "@/lib/utils"

type Props = {
  onPointerDown: (e: React.PointerEvent) => void
  /** Which edge of the parent the handle sits on. Parent must be `relative`. */
  edge?: "right" | "left"
  className?: string
  "data-testid"?: string
}

/**
 * A thin vertical drag handle for resizing a panel. The hit area is wider
 * (w-3) than the visible 1px line for easier grabbing. Place inside a
 * `relative` container; pair with {@link useResizable}.
 */
export function ResizeHandle({
  onPointerDown,
  edge = "right",
  className,
  ...rest
}: Props) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize panel"
      data-testid={rest["data-testid"]}
      onPointerDown={onPointerDown}
      className={cn(
        "group absolute inset-y-0 z-10 w-3 cursor-col-resize bg-transparent",
        edge === "left" ? "left-0" : "right-0",
        className,
      )}
    >
      <div
        className={cn(
          "pointer-events-none absolute inset-y-0 w-1 group-hover:bg-primary/50",
          edge === "left" ? "left-0" : "right-0",
        )}
      />
    </div>
  )
}
