"use client"
import { useCallback, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { RecordsTable } from "@/components/ui/records-table"
import { cn } from "@/lib/utils"

type JournalDate = { date: string; size: number }
type Turn = { question: string; answer: string }

const PROSE =
  "prose prose-sm max-w-none dark:prose-invert prose-a:text-blue-600 " +
  "hover:prose-a:underline dark:prose-a:text-blue-400"

/** Join the `data:` lines of one raw SSE event block into text. */
function parseSseEvent(raw: string): string {
  return raw
    .split("\n")
    .filter((l) => l.startsWith("data:"))
    .map((l) => l.slice(5).replace(/^ /, ""))
    .join("\n")
}

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
      const data = parseSseEvent(buffer.slice(0, sep))
      buffer = buffer.slice(sep + 2)
      if (data) yield data
    }
  }
  // Flush a trailing event that wasn't terminated by a final "\n\n".
  const tail = parseSseEvent(buffer)
  if (tail) yield tail
}

export function JournalScreen() {
  const [dates, setDates] = useState<JournalDate[]>([])
  const [datesError, setDatesError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  // Mirror of `selected` so async callbacks (brainstorm streaming) read the
  // live selection instead of the value captured when they started.
  const selectedRef = useRef<string | null>(null)
  useEffect(() => {
    selectedRef.current = selected
  }, [selected])
  const [content, setContent] = useState("")
  // Monotonic id so a slow earlier loadEntry can't overwrite a newer selection.
  const entryReqSeq = useRef(0)
  const [entry, setEntry] = useState("")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const [question, setQuestion] = useState("")
  const [turns, setTurns] = useState<Turn[]>([])
  const [brainstorming, setBrainstorming] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)

  const loadDates = useCallback(async () => {
    try {
      setDatesError(null)
      const res = await fetch("/api/journal", { cache: "no-store" })
      if (!res.ok) {
        setDatesError(`Failed to load entries (HTTP ${res.status})`)
        return
      }
      const data = (await res.json()) as { dates: JournalDate[] }
      setDates(data.dates)
      return data.dates
    } catch (e) {
      setDatesError(`Failed to load entries: ${String(e)}`)
    }
  }, [])

  const loadEntry = useCallback(async (date: string) => {
    const seq = ++entryReqSeq.current
    setSelected(date)
    const res = await fetch(`/api/journal/${date}`, { cache: "no-store" })
    // Ignore a stale response that lost the race to a newer selection.
    if (seq !== entryReqSeq.current) return
    if (!res.ok) {
      setContent("")
      return
    }
    const data = (await res.json()) as { content: string }
    if (seq !== entryReqSeq.current) return
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

  // Append text to the answer of the most recent (in-flight) turn.
  const appendToLastAnswer = useCallback((chunk: string) => {
    setTurns((prev) => {
      if (prev.length === 0) return prev
      const last = prev[prev.length - 1]
      const answer = last.answer ? `${last.answer}\n${chunk}` : chunk
      return [...prev.slice(0, -1), { ...last, answer }]
    })
  }, [])

  const brainstorm = useCallback(async () => {
    const q = question.trim()
    if (!q || brainstorming) return
    setBrainstorming(true)
    setChatError(null)
    setTurns((prev) => [...prev, { question: q, answer: "" }])
    setQuestion("")
    // Remove the pending placeholder turn so a failed/empty stream doesn't
    // leave a permanent "Thinking…" bubble in the transcript.
    const dropPendingTurn = () => setTurns((prev) => prev.slice(0, -1))
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
        dropPendingTurn()
        return
      }
      const { job_id } = (await post.json()) as { job_id: string }
      const stream = await fetch(`/api/chat/${job_id}/stream`, { cache: "no-store" })
      if (!stream.ok || !stream.body) {
        setChatError(`Stream failed (HTTP ${stream.status})`)
        dropPendingTurn()
        return
      }
      let answer = ""
      for await (const chunk of readSse(stream.body)) {
        answer = answer ? `${answer}\n${chunk}` : chunk
        appendToLastAnswer(chunk)
      }
      if (!answer) {
        setChatError("Brainstorm returned an empty answer.")
        dropPendingTurn()
        return
      }
      // Auto-save the completed Q&A turn to today's journal file.
      const content = `### Brainstorm\n\n**Q:** ${q}\n\n${answer}`
      const res = await fetch("/api/journal", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content }),
      })
      if (!res.ok) {
        const body = await res.text()
        setChatError(`Auto-save failed (HTTP ${res.status}): ${body}`)
        return
      }
      const { date } = (await res.json()) as { date: string }
      await loadDates()
      // Use the live selection (ref) so switching dates mid-stream doesn't
      // yank the view back to a stale selection.
      if (selectedRef.current === date) await loadEntry(date)
    } catch (e) {
      setChatError(String(e))
    } finally {
      setBrainstorming(false)
    }
  }, [question, brainstorming, appendToLastAnswer, loadDates, loadEntry])

  const sortedDates = [...dates].sort((a, b) => b.date.localeCompare(a.date))

  return (
    <div className="flex flex-col gap-6">
      {/* Entries table */}
      <section className="rounded-lg border bg-card">
        <div className="px-4 pt-4 pb-2">
          <h3 className="text-sm font-semibold">Entries</h3>
        </div>
        {datesError ? (
          <p className="px-4 pb-4 text-sm text-destructive">{datesError}</p>
        ) : dates.length === 0 ? (
          <p className="px-4 pb-4 text-sm text-muted-foreground">No entries yet.</p>
        ) : (
          <RecordsTable columns={[{ label: "Date" }, { label: "Size (KB)" }]}>
            {sortedDates.map((d) => (
              <tr
                key={d.date}
                tabIndex={0}
                aria-selected={selected === d.date}
                onClick={() => void loadEntry(d.date)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    void loadEntry(d.date)
                  }
                }}
                className={cn(
                  "cursor-pointer border-b text-xs transition-colors last:border-0",
                  selected === d.date
                    ? "bg-accent font-medium text-accent-foreground"
                    : "hover:bg-accent/50",
                )}
              >
                <td className="px-3 py-2 tabular-nums">{d.date}</td>
                <td className="px-3 py-2 tabular-nums text-muted-foreground">
                  {(d.size / 1024).toFixed(1)}
                </td>
              </tr>
            ))}
          </RecordsTable>
        )}
      </section>

      {/* Full-width: record + view + brainstorm */}
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

        <section className="flex flex-col gap-3 rounded-lg border bg-card p-4">
          <div>
            <h3 className="text-sm font-semibold">Brainstorm with Claude</h3>
            <p className="text-xs text-muted-foreground">
              Ask anything — Claude uses your recent journal entries as context.
              Answers are saved to today&apos;s journal automatically.
            </p>
          </div>

          {/* Conversation transcript (oldest first, like a chat thread). */}
          {turns.length > 0 && (
            <div className="flex flex-col gap-4">
              {turns.map((turn, i) => (
                <div key={i} className="flex flex-col gap-2">
                  <div className="self-end rounded-2xl rounded-br-sm bg-primary px-4 py-2 text-sm text-primary-foreground">
                    {turn.question}
                  </div>
                  <div className={cn(PROSE, "rounded-2xl rounded-bl-sm border bg-background px-4 py-2")}>
                    {turn.answer ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.answer}</ReactMarkdown>
                    ) : (
                      <span className="text-sm text-muted-foreground">Thinking…</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Composer pinned below the transcript, so follow-ups read top-down. */}
          <div className="flex flex-col gap-2">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                // Enter sends; Shift+Enter inserts a newline. Ignore Enter
                // while an IME is composing (Japanese/CJK candidate confirm).
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault()
                  void brainstorm()
                }
              }}
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
          </div>
        </section>
      </div>
    </div>
  )
}
