// Monochrome, 2D line icons for the workspace tree. All use `currentColor` so
// they inherit text color in light/dark themes.

type IconProps = { className?: string }

const base = {
  width: 16,
  height: 16,
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.4,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
}

export function FolderIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden>
      <path d="M1.75 4.25c0-.55.45-1 1-1h3l1.5 1.5h5c.55 0 1 .45 1 1v5.5c0 .55-.45 1-1 1H2.75c-.55 0-1-.45-1-1v-6z" />
    </svg>
  )
}

export function FileIcon({ className, color }: IconProps & { color?: string }) {
  return (
    <svg {...base} stroke={color ?? base.stroke} className={className} aria-hidden>
      <path d="M4 1.75h5l3 3v9.5c0 .14-.11.25-.25.25H4a.25.25 0 0 1-.25-.25V2A.25.25 0 0 1 4 1.75z" />
      <path d="M9 1.75v3h3" />
    </svg>
  )
}

export function ChevronIcon({
  className,
  open,
}: IconProps & { open: boolean }) {
  return (
    <svg
      {...base}
      className={className}
      style={{ transform: open ? "rotate(90deg)" : undefined }}
      aria-hidden
    >
      <path d="M6 4l4 4-4 4" />
    </svg>
  )
}

// Two chevrons pointing apart (unfold), for "expand all".
export function ExpandAllIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden>
      <path d="M4 5.5l4 3 4-3" />
      <path d="M4 9.5l4 3 4-3" />
    </svg>
  )
}

// Two chevrons pointing together (fold), for "collapse all".
export function CollapseAllIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden>
      <path d="M4 10.5l4-3 4 3" />
      <path d="M4 6.5l4-3 4 3" />
    </svg>
  )
}

export function SearchIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden>
      <circle cx="6.75" cy="6.75" r="4" />
      <path d="M9.75 9.75L13.25 13.25" />
    </svg>
  )
}
