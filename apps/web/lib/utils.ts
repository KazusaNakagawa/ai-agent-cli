import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
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
