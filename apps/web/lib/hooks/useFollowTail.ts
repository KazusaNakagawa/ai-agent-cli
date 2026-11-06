"use client"
import { useCallback, useLayoutEffect, useRef } from "react"

import type { ChatMessage } from "@/lib/chatStore"

// Slack that still counts as "at the bottom", so a reader a few pixels short
// of the end keeps following.
const BOTTOM_THRESHOLD_PX = 40

/**
 * Keeps a scrolling log pinned to its latest message. Following pauses while
 * the reader is scrolled up and resumes when they return to the bottom; a new
 * user message always resumes it.
 *
 * Wire `ref` and `onScroll` onto the scroll container.
 */
export function useFollowTail(messages: ChatMessage[]) {
  const ref = useRef<HTMLDivElement>(null)
  const followingRef = useRef(true)
  const userCountRef = useRef(0)

  const onScroll = useCallback(() => {
    const el = ref.current
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    followingRef.current = distance <= BOTTOM_THRESHOLD_PX
  }, [])

  // Runs before paint so a token never flashes below the fold, and so a
  // restored history opens at its end instead of jumping there.
  useLayoutEffect(() => {
    const userCount = messages.filter((m) => m.role === "user").length
    if (userCount > userCountRef.current) followingRef.current = true
    userCountRef.current = userCount
    const el = ref.current
    if (el && followingRef.current) el.scrollTop = el.scrollHeight
  }, [messages])

  return { ref, onScroll }
}
