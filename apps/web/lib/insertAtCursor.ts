// Splice `text` into a textarea's value at the current caret/selection and
// return the new value. The caller owns the value state; this also restores
// focus and places the caret just after the inserted text on the next frame.
export function insertAtCursor(
  textarea: HTMLTextAreaElement | null,
  value: string,
  text: string,
): string {
  if (!textarea) return value + text
  const start = textarea.selectionStart ?? value.length
  const end = textarea.selectionEnd ?? value.length
  const next = value.slice(0, start) + text + value.slice(end)
  // Restore the caret after React re-renders with the new value.
  const caret = start + text.length
  requestAnimationFrame(() => {
    textarea.focus()
    textarea.setSelectionRange(caret, caret)
  })
  return next
}
