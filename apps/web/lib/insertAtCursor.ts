// Splice `text` into a textarea's value at the current caret/selection and
// return the new value. The caller owns the value state; this also restores
// focus and places the caret just after the inserted text on the next frame.
export function insertAtCursor(
  textarea: HTMLTextAreaElement | null,
  value: string,
  text: string,
): string {
  if (!textarea) return value + text
  // Slice against the live DOM value, not the passed `value`. The caller may
  // have captured `value` at render time (e.g. before an async upload), but the
  // caret indices come from the live element — reading the base string from the
  // same source keeps them in sync so characters typed mid-upload aren't lost.
  const base = textarea.value
  const start = textarea.selectionStart ?? base.length
  const end = textarea.selectionEnd ?? base.length
  const next = base.slice(0, start) + text + base.slice(end)
  // Restore the caret after React re-renders with the new value.
  const caret = start + text.length
  requestAnimationFrame(() => {
    textarea.focus()
    textarea.setSelectionRange(caret, caret)
  })
  return next
}
