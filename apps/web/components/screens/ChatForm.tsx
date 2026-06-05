"use client"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { ChatComposer } from "@/components/chat/ChatComposer"
import { ChatMessageList } from "@/components/chat/ChatMessageList"
import { SessionExpiredCard } from "@/components/SessionExpiredCard"
import { useChatState } from "@/lib/chatStore"
import { useAbortableMount } from "@/lib/hooks/useAbortableMount"
import { useChatHistoryNavigation } from "@/lib/hooks/useChatHistoryNavigation"
import { useDraftPersistence } from "@/lib/hooks/useDraftPersistence"
import { useNotionCredentials } from "@/lib/hooks/useNotionCredentials"
import { useNotionSave } from "@/lib/hooks/useNotionSave"
import { useSpeechRecognition } from "@/lib/hooks/useSpeechRecognition"
import { formatLocalDate } from "@/lib/utils"

type SSEEvent = { type: string; data: string }

function today(): string {
  return formatLocalDate()
}

// Parse buffered SSE text. Events are terminated by a blank line ("\n\n");
// multi-line `data:` fields are joined with "\n" per the SSE spec.
function parseSSE(buffer: string): { events: SSEEvent[]; rest: string } {
  const events: SSEEvent[] = []
  let rest = buffer
  let idx
  while ((idx = rest.indexOf("\n\n")) !== -1) {
    const raw = rest.slice(0, idx)
    rest = rest.slice(idx + 2)
    let type = "message"
    const data: string[] = []
    for (const line of raw.split("\n")) {
      if (line.startsWith("event: ")) type = line.slice(7)
      else if (line.startsWith("data: ")) data.push(line.slice(6))
    }
    events.push({ type, data: data.join("\n") })
  }
  return { events, rest }
}

export function ChatForm() {
  const { messages, setMessages } = useChatState()
  const { draft: input, setDraft: setInput } = useDraftPersistence({
    storageKey: "ai-agent:chat-draft:v1",
  })
  const [busy, setBusy] = useState(false)
  const [sessionExpired, setSessionExpired] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const { notionReady } = useNotionCredentials()
  const { supportsMic, listening, toggle: toggleMic } = useSpeechRecognition({
    onTranscript: setInput,
  })
  const { notionState, saveToNotion } = useNotionSave({ messages })

  // Suppress setState and cancel in-flight work after unmount.
  const { mountedRef, abortRef } = useAbortableMount()
  // Shell-style Up/Down history of prior user questions (Issue #117).
  const userHistory = useMemo(
    () => messages.filter((m) => m.role === "user").map((m) => m.content),
    [messages],
  )
  const onHistoryKeyDown = useChatHistoryNavigation({
    history: userHistory,
    setInput,
    busy,
  })
  // The question currently in flight — restored into the textarea on cancel
  // so the user can edit and resend without retyping.
  const pendingQuestionRef = useRef("")

  // Drive one chat turn: POST kicks off a backend job (returns 202 + job_id),
  // then GET /api/chat/{job_id}/stream tails the SSE buffer to completion.
  // Returns "stale" iff the backend emitted the `stale_session` event — the
  // caller retries exactly once.
  const stream = useCallback(
    async (
      question: string,
      ctl: AbortController,
    ): Promise<"ok" | "stale" | "401"> => {
      const post = await fetch("/api/chat", {
        method: "POST",
        cache: "no-store",
        signal: ctl.signal,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ date: today(), question }),
      })
      if (post.status === 401) return "401"
      if (!post.ok) {
        const text = await post.text().catch(() => "")
        throw new Error(`POST /api/chat failed (HTTP ${post.status}): ${text}`)
      }
      const { job_id: jobId } = (await post.json()) as { job_id?: string }
      if (!jobId) throw new Error("POST /api/chat returned no job_id")

      const res = await fetch(`/api/chat/${jobId}/stream`, {
        method: "GET",
        cache: "no-store",
        signal: ctl.signal,
      })
      if (res.status === 401) return "401"
      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => "")
        throw new Error(
          `GET /api/chat/${jobId}/stream failed (HTTP ${res.status}): ${text}`,
        )
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      let stale = false
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const { events, rest } = parseSSE(buffer)
        buffer = rest
        for (const ev of events) {
          if (ctl.signal.aborted || !mountedRef.current) return "ok"
          if (ev.type === "message") {
            setMessages((prev) => {
              const copy = [...prev]
              const last = copy[copy.length - 1]
              if (last && last.role === "assistant") {
                copy[copy.length - 1] = {
                  ...last,
                  content: last.content + (last.content ? "\n" : "") + ev.data,
                }
              }
              return copy
            })
          } else if (ev.type === "stale_session") {
            stale = true
          } else if (ev.type === "error") {
            setMessages((prev) => {
              const copy = [...prev]
              const last = copy[copy.length - 1]
              if (last && last.role === "assistant") {
                copy[copy.length - 1] = {
                  ...last,
                  error: ev.data || "stream error",
                }
              }
              return copy
            })
          }
        }
      }
      return stale ? "stale" : "ok"
    },
    [mountedRef, setMessages],
  )

  const send = useCallback(async () => {
    const question = input.trim()
    if (!question || busy) return

    abortRef.current?.abort()
    const ctl = new AbortController()
    abortRef.current = ctl
    pendingQuestionRef.current = question

    setInput("")
    setBusy(true)
    setRetrying(false)
    setSessionExpired(false)
    setMessages((prev) => [
      ...prev,
      { role: "user", content: question },
      { role: "assistant", content: "" },
    ])

    try {
      let result = await stream(question, ctl)
      if (result === "401") {
        setSessionExpired(true)
        return
      }
      if (result === "stale") {
        // Backend wiped .sessions/<date>; a single retry creates a fresh
        // session and proceeds. Clear any partial output before re-streaming.
        if (!mountedRef.current) return
        setRetrying(true)
        setMessages((prev) => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last && last.role === "assistant") {
            copy[copy.length - 1] = { ...last, content: "", error: null }
          }
          return copy
        })
        result = await stream(question, ctl)
        if (result === "401") {
          setSessionExpired(true)
          return
        }
      }
    } catch (e) {
      if (ctl.signal.aborted || !mountedRef.current) return
      setMessages((prev) => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last && last.role === "assistant") {
          copy[copy.length - 1] = {
            ...last,
            error: e instanceof Error ? e.message : "Network error",
          }
        }
        return copy
      })
    } finally {
      if (mountedRef.current) {
        setBusy(false)
        setRetrying(false)
      }
    }
  }, [abortRef, busy, input, mountedRef, setInput, setMessages, stream])

  // Abort the in-flight stream, mark the last assistant message as cancelled
  // (distinct visual from an error), and restore the original question into
  // the textarea so the user can edit and resend. `busy` flips back to false
  // via send()'s finally{} once the abort propagates through the reader.
  const cancel = useCallback(() => {
    const ctl = abortRef.current
    if (!ctl || !busy) return
    ctl.abort()
    // Esc fires at window scope, so a late keystroke could land after unmount —
    // skip the state writes if so. abort() above is safe either way.
    if (!mountedRef.current) return
    setInput(pendingQuestionRef.current)
    setMessages((prev) => {
      const copy = [...prev]
      const last = copy[copy.length - 1]
      if (last && last.role === "assistant") {
        copy[copy.length - 1] = { ...last, cancelled: true, error: null }
      }
      return copy
    })
  }, [abortRef, busy, mountedRef, setInput, setMessages])

  // Window-level Esc handler — only active while streaming so it doesn't
  // intercept Esc in other contexts (modals, popovers).
  useEffect(() => {
    if (!busy) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault()
        cancel()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [busy, cancel])

  if (sessionExpired) {
    return <SessionExpiredCard />
  }

  return (
    <div className="space-y-4">
      <ChatMessageList
        messages={messages}
        busy={busy}
        retrying={retrying}
        notionReady={notionReady}
        notionState={notionState}
        onNotionSave={(idx) => void saveToNotion(idx)}
      />
      <ChatComposer
        input={input}
        setInput={setInput}
        busy={busy}
        supportsMic={supportsMic}
        listening={listening}
        onToggleMic={toggleMic}
        onSend={() => void send()}
        onCancel={cancel}
        onHistoryKeyDown={onHistoryKeyDown}
      />
    </div>
  )
}
