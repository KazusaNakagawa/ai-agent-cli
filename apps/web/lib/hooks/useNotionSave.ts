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
  // Fire the save automatically as soon as an answer is committed, instead of
  // waiting for a click. Gated on the Notion credentials being present, since
  // the save targets both Notion and the local markdown in one request.
  autoSave?: boolean
  // Whether `messages` has finished rehydrating from sessionStorage. Auto-save
  // must not fire for a restored history, so it only considers messages that
  // appear *after* the first hydrated render.
  hydrated?: boolean
  // Called with the appended markdown path once a save has actually landed in
  // the local mirror (`local_saved === true`). Lets a host refresh whatever it
  // is rendering from that file.
  onLocalSave?: (path: string) => void
}

export type UseNotionSave = {
  notionState: Record<number, NotionSaveState>
  saveToNotion: (idx: number) => Promise<void>
}

// Per-message Notion save state. Keyed by message index — transient by
// design (not part of the persisted chat history) because the Notion page
// itself is the durable artifact.
export function useNotionSave({
  messages,
  autoSave = false,
  hydrated = false,
  onLocalSave,
}: Options): UseNotionSave {
  const [notionState, setNotionState] = useState<
    Record<number, NotionSaveState>
  >({})
  const mountedRef = useRef(true)
  // Held in a ref so an inline callback from the caller doesn't rebuild
  // `saveToNotion` on every render (and re-arm the auto-save effect with it).
  const onLocalSaveRef = useRef(onLocalSave)
  onLocalSaveRef.current = onLocalSave
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
        if (body.local_saved && body.local_path) {
          onLocalSaveRef.current?.(body.local_path)
        }
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

  // Baseline = how many messages existed on the first hydrated render. Every
  // index below it came from sessionStorage and was already saved in its own
  // session, so a reload must not re-append it.
  const baselineRef = useRef<number | null>(null)
  const autoSavedRef = useRef<Set<number>>(new Set())
  useEffect(() => {
    if (!hydrated) return
    if (baselineRef.current === null) {
      baselineRef.current = messages.length
      return
    }
    if (!autoSave) return
    for (let i = baselineRef.current; i < messages.length; i++) {
      const m = messages[i]
      // Skip failed / cancelled turns: there is no answer worth persisting.
      if (m.role !== "assistant" || !m.content || m.error || m.cancelled) continue
      if (autoSavedRef.current.has(i)) continue
      autoSavedRef.current.add(i)
      void saveToNotion(i)
    }
  }, [hydrated, autoSave, messages, saveToNotion])

  return { notionState, saveToNotion }
}
