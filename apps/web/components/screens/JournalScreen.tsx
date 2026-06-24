"use client"
import { useCallback, useEffect, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { cn } from "@/lib/utils"

type JournalDate = { date: string; size: number }

const PROSE =
  "prose prose-sm max-w-none dark:prose-invert prose-a:text-blue-600 " +
  "hover:prose-a:underline dark:prose-a:text-blue-400"

/** Parse a Server-Sent Events stream, yielding the joined `data:` text per event. */
async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const data = raw
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).replace(/^ /, ""))
        .join("\n")
      if (data) yield data
    }
  }
}

export function JournalScreen() {
  const [dates, setDates] = useState<JournalDate[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [content, setContent] = useState("")
  const [entry, setEntry] = useState("")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const [question, setQuestion] = useState("")
  const [answer, setAnswer] = useState("")
  const [brainstorming, setBrainstorming] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)

  const loadDates = useCallback(async () => {
    const res = await fetch("/api/journal", { cache: "no-store" })
    if (!res.ok) return
    const data = (await res.json()) as { dates: JournalDate[] }
    setDates(data.dates)
    return data.dates
  }, [])

  const loadEntry = useCallback(async (date: string) => {
    setSelected(date)
    const res = await fetch(`/api/journal/${date}`, { cache: "no-store" })
    if (!res.ok) {
      setContent("")
      return
    }
    const data = (await res.json()) as { content: string }
    setContent(data.content)
  }, [])

  useEffect(() => {
    void loadDates()
  }, [loadDates])

  const save = useCallback(async () => {
    const text = entry.trim()
    if (!text || saving) return
    setSaving(true)
    setSaveError(null)
    try {
      const res = await fetch("/api/journal", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content: text }),
      })
      if (!res.ok) {
        const body = await res.text()
        setSaveError(`Save failed (HTTP ${res.status}): ${body}`)
        return
      }
      const { date } = (await res.json()) as { date: string }
      setEntry("")
      await loadDates()
      await loadEntry(date)
    } catch (e) {
      setSaveError(String(e))
    } finally {
      setSaving(false)
    }
  }, [entry, saving, loadDates, loadEntry])

  const brainstorm = useCallback(async () => {
    const q = question.trim()
    if (!q || brainstorming) return
    setBrainstorming(true)
    setChatError(null)
    setAnswer("")
    try {
      const post = await fetch("/api/journal/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: q }),
      })
      if (!post.ok) {
        const body = await post.text()
        setChatError(
          post.status === 404
            ? "No journal entries yet — record something first."
            : `Brainstorm failed (HTTP ${post.status}): ${body}`,
        )
        return
      }
      const { job_id } = (await post.json()) as { job_id: string }
      const stream = await fetch(`/api/chat/${job_id}/stream`, { cache: "no-store" })
      if (!stream.ok || !stream.body) {
        setChatError(`Stream failed (HTTP ${stream.status})`)
        return
      }
      for await (const chunk of readSse(stream.body)) {
        setAnswer((prev) => (prev ? `${prev}\n${chunk}` : chunk))
      }
    } catch (e) {
      setChatError(String(e))
    } finally {
      setBrainstorming(false)
    }
  }, [question, brainstorming])

  return (
    <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
      {/* Left: date list */}
      <aside className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-muted-foreground">Entries</h3>
        {dates.length === 0 ? (
          <p className="text-sm text-muted-foreground">No entries yet.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {dates.map((d) => (
              <li key={d.date}>
                <button
                  type="button"
                  onClick={() => void loadEntry(d.date)}
                  className={cn(
                    "w-full rounded-md px-3 py-2 text-left text-sm transition-colors",
                    selected === d.date
                      ? "bg-accent font-medium text-accent-foreground"
                      : "hover:bg-accent/50",
                  )}
                >
                  {d.date}
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      {/* Right: record + view + brainstorm */}
      <div className="flex flex-col gap-6">
        <section className="flex flex-col gap-2 rounded-lg border bg-card p-4">
          <h3 className="text-sm font-semibold">Record today</h3>
          <textarea
            value={entry}
            onChange={(e) => setEntry(e.target.value)}
            placeholder="What happened today? What are you thinking about?"
            rows={5}
            className="w-full resize-y rounded-md border bg-background p-3 text-sm"
          />
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving || entry.trim() === ""}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save entry"}
            </button>
            {saveError && <span className="text-sm text-destructive">{saveError}</span>}
          </div>
        </section>

        {selected && (
          <section className="flex flex-col gap-2 rounded-lg border bg-card p-4">
            <h3 className="text-sm font-semibold">{selected}</h3>
            <div className={PROSE}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            </div>
          </section>
        )}

        <section className="flex flex-col gap-2 rounded-lg border bg-card p-4">
          <h3 className="text-sm font-semibold">Brainstorm with Claude</h3>
          <p className="text-xs text-muted-foreground">
            Ask anything — Claude uses your recent journal entries as context.
          </p>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. What should I focus on next based on this week?"
            rows={3}
            className="w-full resize-y rounded-md border bg-background p-3 text-sm"
          />
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void brainstorm()}
              disabled={brainstorming || question.trim() === ""}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {brainstorming ? "Thinking…" : "Brainstorm"}
            </button>
            {chatError && <span className="text-sm text-destructive">{chatError}</span>}
          </div>
          {answer && (
            <div className={cn(PROSE, "mt-2 rounded-md border bg-background p-3")}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
