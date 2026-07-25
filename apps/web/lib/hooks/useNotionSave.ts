"use client"
import { useCallback, useEffect, useRef, useState } from "react"

import type { ChatMessage } from "@/lib/chatStore"
import { formatLocalDate } from "@/lib/utils"

type NotionSaveStatus = "idle" | "saving" | "saved" | "error"

export type NotionSaveState = {
  status: NotionSaveStatus
  url?: string
  error?: string
  // Outcome of the local briefing markdown mirror, which the backend writes
  // independently of the Notion save. `localSaved === false` on an otherwise
  // successful save means Notion has the Q&A but the local file does not.
  localPath?: string
  localSaved?: boolean
  localError?: string
}

type Options = {
  messages: ChatMessage[]
}

export type UseNotionSave = {
  notionState: Record<number, NotionSaveState>
  saveToNotion: (idx: number) => Promise<void>
}

// Per-message Notion save state. Keyed by message index — transient by
// design (not part of the persisted chat history) because the Notion page
// itself is the durable artifact.
export function useNotionSave({ messages }: Options): UseNotionSave {
  const [notionState, setNotionState] = useState<
    Record<number, NotionSaveState>
  >({})
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const saveToNotion = useCallback(
    async (idx: number) => {
      const assistant = messages[idx]
      if (!assistant || assistant.role !== "assistant" || !assistant.content) return
      // Walk back to find the user question this answer is responding to.
      let question = ""
      for (let j = idx - 1; j >= 0; j--) {
        if (messages[j].role === "user") {
          question = messages[j].content
          break
        }
      }
      if (!question) return

      setNotionState((prev) => ({ ...prev, [idx]: { status: "saving" } }))
      try {
        const res = await fetch("/api/chat/notion-import", {
          method: "POST",
          cache: "no-store",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            date: formatLocalDate(),
            question,
            answer: assistant.content,
          }),
        })
        if (!res.ok) {
          // AC: surface the backend's `detail` verbatim so the operator
          // sees the skill's own error message (e.g. "page not found").
          let detail = `HTTP ${res.status}`
          try {
            const body = (await res.json()) as { detail?: string }
            if (body.detail) detail = body.detail
          } catch {
            // Body wasn't JSON — keep the HTTP fallback.
          }
          if (!mountedRef.current) return
          setNotionState((prev) => ({
            ...prev,
            [idx]: { status: "error", error: detail },
          }))
          return
        }
        const body = (await res.json()) as {
          url: string
          local_path?: string | null
          local_saved?: boolean
          local_error?: string | null
        }
        if (!mountedRef.current) return
        setNotionState((prev) => ({
          ...prev,
          [idx]: {
            status: "saved",
            url: body.url,
            localPath: body.local_path ?? undefined,
            localSaved: body.local_saved ?? false,
            localError: body.local_error ?? undefined,
          },
        }))
      } catch (e) {
        if (!mountedRef.current) return
        setNotionState((prev) => ({
          ...prev,
          [idx]: {
            status: "error",
            error: e instanceof Error ? e.message : "Network error",
          },
        }))
      }
    },
    [messages],
  )

  return { notionState, saveToNotion }
}
