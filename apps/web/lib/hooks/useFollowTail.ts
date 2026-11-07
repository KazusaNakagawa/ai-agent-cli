"use client"
import { useCallback, useLayoutEffect, useRef } from "react"

// Slack that still counts as "at the bottom", so a reader a few pixels short
// of the end keeps following.
const BOTTOM_THRESHOLD_PX = 40

export type FollowTailOptions = {
  /** Follow from the first render. Off for a log that sits under content the
   * reader should see first (the journal entry). Default true. */
  followFromStart?: boolean
  /** Resume following whenever the number of user messages grows. Off when
   * that count can briefly jump without a new question (the journal shows a
   * committed turn and its pending copy for one render). Default true. */
  followOnNewUserMessage?: boolean
}

/**
 * Keeps a scrolling log pinned to its latest message. Following pauses while
 * the reader is scrolled up and resumes when they return to the bottom. By
 * default it starts on, and a new user message always resumes it; hosts that
 * turn those off drive it with `follow()` / `stopFollowing()` instead.
 *
 * Wire `ref` and `onScroll` onto the scroll container.
 */
export function useFollowTail(
  messages: ReadonlyArray<{ role: string }>,
  { followFromStart = true, followOnNewUserMessage = true }: FollowTailOptions = {}
) {
  const ref = useRef<HTMLDivElement>(null)
  const followingRef = useRef(followFromStart)
  const userCountRef = useRef(0)

  const onScroll = useCallback(() => {
    const el = ref.current
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    followingRef.current = distance <= BOTTOM_THRESHOLD_PX
  }, [])

  const follow = useCallback(() => {
    followingRef.current = true
    const el = ref.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])

  const stopFollowing = useCallback(() => {
    followingRef.current = false
  }, [])

  // Runs before paint so a token never flashes below the fold, and so a
  // restored history opens at its end instead of jumping there.
  useLayoutEffect(() => {
    const userCount = messages.filter((m) => m.role === "user").length
    if (followOnNewUserMessage && userCount > userCountRef.current) {
      followingRef.current = true
    }
    userCountRef.current = userCount
    const el = ref.current
    if (el && followingRef.current) el.scrollTop = el.scrollHeight
  }, [messages, followOnNewUserMessage])

  return { ref, onScroll, follow, stopFollowing }
}
