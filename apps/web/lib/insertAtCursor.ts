import type { RefObject } from "react"

export function insertAtCursor(
  ref: RefObject<HTMLTextAreaElement>,
  setValue: (v: string) => void,
  snippet: string
): void {
  const el = ref.current
  if (!el) return
  const start = el.selectionStart ?? el.value.length
  const end = el.selectionEnd ?? el.value.length
  const next = el.value.slice(0, start) + snippet + el.value.slice(end)
  setValue(next)
  // Restore focus and move caret after snippet
  requestAnimationFrame(() => {
    el.focus()
    el.selectionStart = start + snippet.length
    el.selectionEnd = start + snippet.length
  })
}
