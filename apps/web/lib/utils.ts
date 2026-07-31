import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Last path segment, e.g. "src/app.py" -> "app.py".
 *
 * Trailing separators are trimmed first, so "a/b/" yields "b" rather than "".
 * Both separators are treated as such: paths reach the UI as strings built by
 * the host's `Path`, and a Windows-style one must still match a filename-keyed
 * list. The trade-off is that a POSIX filename containing a literal backslash
 * would be split — pathological enough to be worth the cross-platform safety.
 */
export function basename(path: string): string {
  const trimmed = path.replace(/[\\/]+$/, "")
  const segments = trimmed.split(/[\\/]/)
  return segments[segments.length - 1] || path
}

// YYYY-MM-DD in the browser's local timezone. `toISOString()` would return
// UTC, which silently shifts the date in non-UTC zones (e.g. 07:47 JST is
// still the previous UTC day) and lands appends on yesterday's briefing.
export function formatLocalDate(d: Date = new Date()): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}
