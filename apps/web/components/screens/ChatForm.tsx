"use client"
import { useCallback, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { SessionExpiredCard } from "@/components/SessionExpiredCard"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { LoadingDots } from "@/components/ui/loading-dots"
import { useChatState } from "@/lib/chatStore"
import { useAbortableMount } from "@/lib/hooks/useAbortableMount"
import { cn } from "@/lib/utils"

type SSEEvent = { type: string; data: string }

type NotionSaveStatus = "idle" | "saving" | "saved" | "error"

type NotionSaveState = {
  status: NotionSaveStatus
  url?: string
  error?: string
}

type NotionModel = "sonnet" | "opus" | "haiku"

// Bumped if the persisted shape changes incompatibly.
const DRAFT_STORAGE_KEY = "ai-agent:chat-draft:v1"

function loadDraft(): string {
  if (typeof window === "undefined") return ""
  try {
    return window.sessionStorage.getItem(DRAFT_STORAGE_KEY) ?? ""
  } catch {
    return ""
  }
}

function persistDraft(draft: string) {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(DRAFT_STORAGE_KEY, draft)
  } catch {
    // quota / unavailable — draft remains in memory for the tab
  }
}

function clearDraft() {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.removeItem(DRAFT_STORAGE_KEY)
  } catch {
    // ignore
  }
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
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

// SpeechRecognition globals — typed loosely because the TS DOM lib omits them.
type Recognition = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult:
    | ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void)
    | null
  onend: (() => void) | null
  onerror: ((e: { error: string }) => void) | null
  start(): void
  stop(): void
}
type RecognitionCtor = new () => Recognition

function NotionSaveRow({
  state,
  enabled,
  model,
  onModelChange,
  onSave,
}: {
  state: NotionSaveState | undefined
  enabled: boolean
  model: NotionModel
  onModelChange: (m: NotionModel) => void
  onSave: () => void
}) {
  const status: NotionSaveStatus = state?.status ?? "idle"
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
      <select
        value={model}
        onChange={(e) => onModelChange(e.target.value as NotionModel)}
        disabled={status === "saving"}
        className="h-8 rounded-md border bg-background px-2 text-xs"
        data-testid="notion-model-select"
        title="このリクエストで claude CLI に渡すモデル"
      >
        <option value="sonnet">sonnet</option>
        <option value="opus">opus</option>
        <option value="haiku">haiku</option>
      </select>
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

function getRecognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor
    webkitSpeechRecognition?: RecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export function ChatForm() {
  const { messages, setMessages } = useChatState()
  // Render "" on first paint so SSR and the first client render agree
  // (sessionStorage is unavailable on the server). The hydrate effect
  // below promotes input to whatever draft was persisted in this tab.
  const [input, setInput] = useState("")
  const [hydrated, setHydrated] = useState(false)
  const [busy, setBusy] = useState(false)
  const [sessionExpired, setSessionExpired] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [listening, setListening] = useState(false)
  const [supportsMic, setSupportsMic] = useState(false)
  // null until /api/credentials answers; the Notion button stays disabled
  // until we know whether both NOTION_* keys exist (no premature enable).
  const [creds, setCreds] = useState<Record<string, boolean> | null>(null)
  // Per-message Notion save state. Keyed by message index — transient by
  // design (not part of the persisted chat history) because the Notion
  // page itself is the durable artifact.
  const [notionState, setNotionState] = useState<
    Record<number, NotionSaveState>
  >({})
  const [notionModel, setNotionModel] = useState<NotionModel>("sonnet")

  // Suppress setState and cancel in-flight work after unmount.
  const { mountedRef, abortRef } = useAbortableMount()
  const recRef = useRef<Recognition | null>(null)

  useEffect(() => {
    setSupportsMic(getRecognitionCtor() !== null)
    setInput(loadDraft())
    setHydrated(true)
    return () => {
      recRef.current?.stop()
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetch("/api/credentials", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: Record<string, boolean> | null) => {
        if (cancelled) return
        setCreds(data ?? {})
      })
      .catch(() => {
        // Network failure — leave creds null so the button stays disabled
        // rather than enabling it on incomplete information.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const notionReady = Boolean(
    creds && creds.NOTION_API_KEY && creds.NOTION_DATABASE_ID,
  )

  useEffect(() => {
    if (!hydrated) return
    if (input === "") {
      clearDraft()
    } else {
      persistDraft(input)
    }
  }, [input, hydrated])

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
  }, [abortRef, busy, input, mountedRef, setMessages, stream])

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
            date: today(),
            question,
            answer: assistant.content,
            model: notionModel,
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
        const body = (await res.json()) as { url: string }
        if (!mountedRef.current) return
        setNotionState((prev) => ({
          ...prev,
          [idx]: { status: "saved", url: body.url },
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
    [messages, mountedRef, notionModel],
  )

  const toggleMic = useCallback(() => {
    if (listening) {
      recRef.current?.stop()
      return
    }
    const Ctor = getRecognitionCtor()
    if (!Ctor) return
    const rec = new Ctor()
    rec.lang = "ja-JP"
    rec.continuous = true
    rec.interimResults = true
    rec.onresult = (e) => {
      let transcript = ""
      for (let i = 0; i < e.results.length; i++) {
        transcript += e.results[i][0].transcript
      }
      setInput(transcript)
    }
    const stop = () => {
      if (mountedRef.current) setListening(false)
      recRef.current = null
    }
    rec.onend = stop
    rec.onerror = stop
    rec.start()
    recRef.current = rec
    setListening(true)
  }, [listening, mountedRef])

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
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {m.content}
                      </ReactMarkdown>
                    </div>
                  ) : busy && i === messages.length - 1 ? (
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
                {m.role === "assistant" && m.content && (
                  <NotionSaveRow
                    state={notionState[i]}
                    enabled={notionReady}
                    model={notionModel}
                    onModelChange={setNotionModel}
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
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  void send()
                }
              }}
              placeholder="Ask about today's briefing…"
              rows={2}
              className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm"
              data-testid="chat-input"
              disabled={busy}
            />
            {supportsMic && (
              <Button
                type="button"
                variant={listening ? "destructive" : "outline"}
                onClick={toggleMic}
                data-testid="mic-button"
                aria-pressed={listening}
                title={listening ? "音声入力停止" : "音声入力開始 (ja-JP)"}
              >
                {listening ? "🛑" : "🎤"}
              </Button>
            )}
            <Button
              onClick={() => void send()}
              disabled={busy || input.trim().length === 0}
              data-testid="send-button"
            >
              {busy ? "Sending…" : "Send"}
            </Button>
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
