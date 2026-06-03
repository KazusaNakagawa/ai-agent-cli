"use client"
import { useCallback, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"
import remarkGfm from "remark-gfm"

import { SessionExpiredCard } from "@/components/SessionExpiredCard"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { LoadingDots } from "@/components/ui/loading-dots"
import { useChatState } from "@/lib/chatStore"
import { useAbortableMount } from "@/lib/hooks/useAbortableMount"
import { useDraftPersistence } from "@/lib/hooks/useDraftPersistence"
import { useNotionCredentials } from "@/lib/hooks/useNotionCredentials"
import {
  useNotionSave,
  type NotionSaveState,
} from "@/lib/hooks/useNotionSave"
import { useSpeechRecognition } from "@/lib/hooks/useSpeechRecognition"
import { cn, formatLocalDate } from "@/lib/utils"

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

function NotionSaveRow({
  state,
  enabled,
  onSave,
}: {
  state: NotionSaveState | undefined
  enabled: boolean
  onSave: () => void
}) {
  const status: NotionSaveState["status"] = state?.status ?? "idle"
  const disabled = !enabled || status === "saving" || status === "saved"
  const title = enabled
    ? undefined
    : "Notion 認証情報が未設定です（Credentials タブで設定してください）"
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onSave}
        disabled={disabled}
        title={title}
        data-testid="notion-save-button"
      >
        {status === "saving"
          ? "追記中…"
          : status === "saved"
          ? "✓ Notion に追記済"
          : "Notion ブリーフィングに追記"}
      </Button>
      {status === "saved" && state?.url && (
        <a
          href={state.url}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline"
          data-testid="notion-save-link"
        >
          ページを開く
        </a>
      )}
      {status === "error" && state?.error && (
        <span
          className="text-destructive"
          data-testid="notion-save-error"
        >
          {state.error}
        </span>
      )}
    </div>
  )
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
  const composingRef = useRef(false)
  // The question currently in flight — restored into the textarea on cancel
  // so the user can edit and resend without retyping.
  const pendingQuestionRef = useRef("")

  // Stream one POST /api/chat round trip. Returns "stale" iff the backend
  // emitted the `stale_session` event — the caller retries exactly once.
  const stream = useCallback(
    async (
      question: string,
      ctl: AbortController,
    ): Promise<"ok" | "stale" | "401"> => {
      const res = await fetch("/api/chat", {
        method: "POST",
        cache: "no-store",
        signal: ctl.signal,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ date: today(), question }),
      })
      if (res.status === 401) return "401"
      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => "")
        throw new Error(`POST /api/chat failed (HTTP ${res.status}): ${text}`)
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
      <Card>
        <CardContent
          className="max-h-[60vh] space-y-3 overflow-y-auto pt-6"
          data-testid="chat-log"
        >
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Ask anything about today&apos;s briefing — e.g.
              {" "}&ldquo;半導体セクターの新着リスクは？&rdquo;
            </p>
          ) : (
            messages.map((m, i) => (
              <div
                key={i}
                className={cn(
                  "rounded-md border p-3 text-sm",
                  m.role === "user"
                    ? "border-primary/30 bg-primary/5"
                    : "border-muted bg-muted/30",
                )}
                data-testid={`chat-msg-${m.role}`}
              >
                <p className="mb-1 text-[10px] font-medium uppercase text-muted-foreground">
                  {m.role}
                </p>
                {m.role === "assistant" ? (
                  m.content ? (
                    <div className="prose prose-sm max-w-none dark:prose-invert">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeSanitize]}
                      >
                        {m.content}
                      </ReactMarkdown>
                    </div>
                  ) : busy && i === messages.length - 1 && !m.cancelled ? (
                    <LoadingDots
                      label="調査中"
                      data-testid="chat-thinking"
                    />
                  ) : null
                ) : (
                  <p className="whitespace-pre-wrap">{m.content}</p>
                )}
                {m.error && (
                  <p
                    className="mt-2 text-xs text-destructive"
                    data-testid="chat-error"
                  >
                    {m.error}
                  </p>
                )}
                {m.role === "assistant" && m.cancelled && (
                  <p
                    className="mt-2 text-xs text-muted-foreground"
                    data-testid="chat-cancelled"
                  >
                    Cancelled
                  </p>
                )}
                {m.role === "assistant" && m.content && (
                  <NotionSaveRow
                    state={notionState[i]}
                    // Disable while this assistant message is still streaming
                    // (last message + busy) so the user can't persist a
                    // partial answer.
                    enabled={
                      notionReady && !(busy && i === messages.length - 1)
                    }
                    onSave={() => void saveToNotion(i)}
                  />
                )}
              </div>
            ))
          )}
          {retrying && (
            <p
              className="text-xs text-muted-foreground"
              data-testid="chat-retrying"
            >
              Session expired upstream, retrying…
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-2 pt-6">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onCompositionStart={() => {
                composingRef.current = true
              }}
              onCompositionEnd={() => {
                composingRef.current = false
              }}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !composingRef.current &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault()
                  void send()
                }
              }}
              placeholder="Ask about today's briefing…"
              rows={2}
              className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm"
              data-testid="chat-input"
            />
            {supportsMic && (
              <Button
                type="button"
                variant={listening ? "destructive" : "outline"}
                onClick={() => toggleMic(input)}
                data-testid="mic-button"
                aria-pressed={listening}
                title={listening ? "音声入力停止" : "音声入力開始 (ja-JP)"}
              >
                {listening ? "🛑" : "🎤"}
              </Button>
            )}
            {busy ? (
              <Button
                type="button"
                variant="destructive"
                onClick={cancel}
                data-testid="cancel-button"
                title="送信中の応答を中止 (Esc)"
              >
                Cancel
              </Button>
            ) : (
              <Button
                onClick={() => void send()}
                disabled={input.trim().length === 0}
                data-testid="send-button"
              >
                Send
              </Button>
            )}
          </div>
          {!supportsMic && (
            <p
              className="text-xs text-muted-foreground"
              data-testid="mic-unsupported"
            >
              Voice input is unavailable in this browser (Chrome / Edge supported).
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
