import type { HTMLAttributes } from "react"

import { cn } from "@/lib/utils"

type Props = HTMLAttributes<HTMLSpanElement> & {
  label?: string
}

// Three bouncing dots used to signal "AI is thinking" / "job is running".
// `label` is announced to screen readers and shown next to the dots when
// passed; pass an empty string to render dots only.
export function LoadingDots({ label = "Thinking", className, ...rest }: Props) {
  return (
    <span
      role="status"
      aria-label={label || "loading"}
      className={cn("inline-flex items-center gap-1.5 text-current", className)}
      {...rest}
    >
      {label && (
        <span className="text-xs text-muted-foreground">{label}</span>
      )}
      <span className="inline-flex items-end gap-1">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current opacity-70 [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current opacity-70 [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current opacity-70" />
      </span>
    </span>
  )
}
