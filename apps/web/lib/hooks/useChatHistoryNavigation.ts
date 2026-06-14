"use client"
import { useCallback, useEffect, useRef, type KeyboardEvent } from "react"

/**
 * Shell-prompt-style history recall for the chat textarea.
 *
 * Up/Down walk back / forward through the user's prior questions. The first
 * Up press snapshots whatever was in the textarea so Down-past-newest (or Esc)
 * can restore it. Mid-navigation edits are *not* preserved across further
 * keystrokes — matching readline/zsh: typing while navigating commits to that
 * draft, then the next Up overwrites it.
 *
 * Caller is responsible for filtering out IME composition before delegating
 * (so Enter-to-send and arrow-history share the same guard at the call site).
 */
export function useChatHistoryNavigation({
  history,
  setInput,
  busy,
}: {
  /** User-question history, oldest → newest. */
  history: string[]
  setInput: (v: string) => void
  /** Streaming flag — Esc is reserved for cancel while busy (Issue #98). */
  busy: boolean
}): (e: KeyboardEvent<HTMLTextAreaElement>) => void {
  // -1 = not navigating. Otherwise an index into ``history``.
  const indexRef = useRef(-1)
  const savedDraftRef = useRef("")

  // After a successful send, the new user message lands in ``history`` and
  // input clears. Reset so the next Up starts a fresh cycle rather than
  // walking from the stale index left behind by a half-navigated state.
  useEffect(() => {
    indexRef.current = -1
    savedDraftRef.current = ""
  }, [history.length])

  return useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      const ta = e.currentTarget

      if (e.key === "ArrowUp") {
        if (history.length === 0) return
        // Multi-line caret guard: when the caret isn't on the first line of
        // a multi-line draft, Up moves the caret naturally — don't hijack.
        const beforeCaret = ta.value.slice(0, ta.selectionStart)
        if (beforeCaret.includes("\n")) return
        e.preventDefault()
        if (indexRef.current === -1) {
          savedDraftRef.current = ta.value
          indexRef.current = history.length - 1
        } else if (indexRef.current > 0) {
          indexRef.current -= 1
        }
        setInput(history[indexRef.current])
        return
      }

      if (e.key === "ArrowDown") {
        if (indexRef.current === -1) return
        const afterCaret = ta.value.slice(ta.selectionEnd)
        if (afterCaret.includes("\n")) return
        e.preventDefault()
        if (indexRef.current < history.length - 1) {
          indexRef.current += 1
          setInput(history[indexRef.current])
        } else {
          // Past newest → restore the pre-nav draft and exit history mode.
          setInput(savedDraftRef.current)
          indexRef.current = -1
          savedDraftRef.current = ""
        }
        return
      }

      if (e.key === "Escape") {
        // Esc while streaming is the cancel hotkey (ChatForm's window-level
        // handler owns that). Letting it bubble keeps cancel taking precedence.
        if (busy) return
        if (indexRef.current === -1) return
        e.preventDefault()
        setInput(savedDraftRef.current)
        indexRef.current = -1
        savedDraftRef.current = ""
      }
    },
    [history, setInput, busy],
  )
}
