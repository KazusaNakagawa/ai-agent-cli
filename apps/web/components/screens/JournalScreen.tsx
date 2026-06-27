"use client"
import { useCallback, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { CloseIcon, TrashIcon } from "@/components/briefing/icons"
import { ResizeHandle } from "@/components/ResizeHandle"
import { ImageAttachArea } from "@/components/ui/ImageAttachArea"
import { useImageDrop } from "@/lib/hooks/useImageDrop"
import { useResizable } from "@/lib/hooks/useResizable"
import type { ImageAttachment } from "@/lib/types/image"
import { cn } from "@/lib/utils"

type JournalEntry = { id: string; date: string; size: number; item: string }
type Turn = { question: string; answer: string }

const PROSE =
  "prose prose-sm max-w-none dark:prose-invert prose-a:text-blue-600 " +
  "hover:prose-a:underline dark:prose-a:text-blue-400"

const HEADER_BTN =
  "rounded p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"

/** Extract HH:MM:SS from an entry id (YYYY-MM-DD_HHMMSS), or null for legacy day ids. */
function entryTime(id: string): string | null {
  const m = id.match(/^\d{4}-\d{2}-\d{2}_(\d{2})(\d{2})(\d{2})/)
  return m ? `${m[1]}:${m[2]}:${m[3]}` : null
}

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
  const tail = parseSseEvent(buffer)
  if (tail) yield tail
}

export function JournalScreen() {
  const [entries, setEntries] = useState<JournalEntry[]>([])
  const [entriesError, setEntriesError] = useState<string | null>(null)
  const [trash, setTrash] = useState<JournalEntry[]>([])
  const [showTrash, setShowTrash] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [composing, setComposing] = useState(false)
  const brainstormRef = useRef<HTMLTextAreaElement>(null)
  const [brainstormImage, setBrainstormImage] = useState<ImageAttachment | null>(null)
  const { isDragging: isBrainstormDragging } = useImageDrop(brainstormRef, setBrainstormImage)
  const [content, setContent] = useState("")
  const entryReqSeq = useRef(0)

  const [question, setQuestion] = useState("")
  const [turns, setTurns] = useState<Turn[]>([])
  const [brainstorming, setBrainstorming] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  // Tracks the journal entry id for the current brainstorm session so that
  // subsequent turns append to the same entry instead of creating new ones.
  const brainstormEntryId = useRef<string | null>(null)

  const { width: listWidth, startResize } = useResizable({
    storageKey: "ai-agent:journal-list-width:v1",
    defaultWidth: 288,
    minWidth: 200,
    maxWidth: 480,
  })

  const loadDates = useCallback(async () => {
    try {
      setEntriesError(null)
      const res = await fetch("/api/journal", { cache: "no-store" })
      if (!res.ok) {
        setEntriesError(`Failed to load entries (HTTP ${res.status})`)
        return
      }
      const data = (await res.json()) as { entries: JournalEntry[] }
      setEntries(data.entries)
      return data.entries
    } catch (e) {
      setEntriesError(`Failed to load entries: ${String(e)}`)
    }
  }, [])

  const loadEntry = useCallback(async (entryId: string) => {
    const seq = ++entryReqSeq.current
    setSelected(entryId)
    setComposing(false)
    // Clear immediately so the previous entry's body can't render under the
    // new header while the fetch is in flight (or if it fails).
    setContent("")
    let res: Response
    try {
      res = await fetch(`/api/journal/${entryId}`, { cache: "no-store" })
    } catch {
      return
    }
    if (seq !== entryReqSeq.current) return
    if (!res.ok) return
    const data = (await res.json()) as { content: string }
    if (seq !== entryReqSeq.current) return
    setContent(data.content)
  }, [])

  useEffect(() => {
    void loadDates()
  }, [loadDates])

  const closePanel = () => {
    setSelected(null)
    setComposing(false)
    brainstormEntryId.current = null
  }

  const startCompose = () => {
    setSelected(null)
    setComposing(true)
  }

  const loadTrash = useCallback(async () => {
    try {
      setEntriesError(null)
      const res = await fetch("/api/journal/trash", { cache: "no-store" })
      if (!res.ok) {
        setEntriesError(`Failed to load trash (HTTP ${res.status})`)
        return
      }
      const data = (await res.json()) as { entries: JournalEntry[] }
      setTrash(data.entries)
    } catch (e) {
      setEntriesError(`Failed to load trash: ${String(e)}`)
    }
  }, [])

  const deleteEntry = useCallback(
    async (entryId: string) => {
      try {
        const res = await fetch(`/api/journal/${entryId}`, { method: "DELETE" })
        if (!res.ok) {
          setEntriesError(`Delete failed (HTTP ${res.status})`)
          return
        }
        // Collapse the panel if the open entry was the one removed.
        setSelected((cur) => (cur === entryId ? null : cur))
        await loadDates()
      } catch (e) {
        setEntriesError(`Delete failed: ${String(e)}`)
      }
    },
    [loadDates],
  )

  const restoreEntry = useCallback(
    async (entryId: string) => {
      try {
        const res = await fetch(`/api/journal/${entryId}/restore`, { method: "POST" })
        if (!res.ok) {
          setEntriesError(`Restore failed (HTTP ${res.status})`)
          return
        }
        await Promise.all([loadDates(), loadTrash()])
      } catch (e) {
        setEntriesError(`Restore failed: ${String(e)}`)
      }
    },
    [loadDates, loadTrash],
  )

  const purgeEntry = useCallback(
    async (entryId: string) => {
      try {
        const res = await fetch(`/api/journal/${entryId}?purge=true`, { method: "DELETE" })
        if (!res.ok) {
          setEntriesError(`Permanent delete failed (HTTP ${res.status})`)
          return
        }
        await loadTrash()
      } catch (e) {
        setEntriesError(`Permanent delete failed: ${String(e)}`)
      }
    },
    [loadTrash],
  )

  // Toggle the trash view, loading its contents when opening. Side effects stay
  // out of the state updater: compute `next`, set it, then conditionally load.
  const toggleTrash = useCallback(() => {
    const next = !showTrash
    setShowTrash(next)
    if (next) void loadTrash()
  }, [showTrash, loadTrash])

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
    const dropPendingTurn = () => setTurns((prev) => prev.slice(0, -1))
    try {
      const post = await fetch("/api/journal/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question: q,
          ...(brainstormImage ? { image_path: brainstormImage.path } : {}),
        }),
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
      const qaBlock = `${q}\n\n${answer}`
      let saveRes: Response
      if (brainstormEntryId.current) {
        // Append to the existing entry for this brainstorm session.
        saveRes = await fetch(`/api/journal/${brainstormEntryId.current}`, {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ content: qaBlock }),
        })
      } else {
        // First turn: create a new entry and remember its id.
        saveRes = await fetch("/api/journal", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ content: qaBlock, item: q.slice(0, 20) }),
        })
        if (saveRes.ok) {
          const saved = (await saveRes.json()) as { id: string }
          brainstormEntryId.current = saved.id
        }
      }
      if (!saveRes.ok) {
        // 404 means the entry was deleted — reset so the next turn creates fresh.
        if (saveRes.status === 404) brainstormEntryId.current = null
        const body = await saveRes.text()
        setChatError(`Auto-save failed (HTTP ${saveRes.status}): ${body}`)
        return
      }
      await loadDates()
      // The brainstorm answer is saved as its own entry; the transcript above
      // already shows it, so leave the current selection untouched.
    } catch (e) {
      setChatError(String(e))
    } finally {
      setBrainstorming(false)
      setBrainstormImage(null)
    }
  }, [question, brainstorming, brainstormImage, appendToLastAnswer, loadDates])

  const sortedEntries = [...entries].sort((a, b) => b.id.localeCompare(a.id))
  const selectedMeta = sortedEntries.find((e) => e.id === selected)
  const panelOpen = selected !== null || composing

  return (
    <div className="flex h-full">
      {/* Left: date list */}
      <div
        style={panelOpen ? { width: listWidth } : undefined}
        className={cn(
          "relative flex-shrink-0 overflow-y-auto",
          panelOpen ? "border-r" : "flex-1",
        )}
      >
        {/* Top bar: New entry + Trash toggle */}
        <div className="flex items-center gap-2 border-b p-2">
          <button
            type="button"
            onClick={startCompose}
            className="flex flex-1 items-center justify-center gap-1 rounded-md border border-dashed px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            <span className="text-base leading-none">+</span> New
          </button>
          <button
            type="button"
            onClick={toggleTrash}
            aria-pressed={showTrash}
            className={cn(
              "flex items-center gap-1 rounded-md border px-3 py-2 text-xs font-medium transition-colors",
              showTrash
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <TrashIcon /> Trash
          </button>
        </div>

        {entriesError && (
          <p className="px-3 py-4 text-sm text-destructive">{entriesError}</p>
        )}

        {showTrash ? (
          trash.length === 0 ? (
            <p className="px-3 py-4 text-sm text-muted-foreground">Trash is empty.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-xs text-muted-foreground">
                  <th className="px-3 py-2 text-left">Item</th>
                  <th className="px-3 py-2 text-left">Deleted</th>
                  <th className="px-3 py-2 text-right">Size (KB)</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {[...trash]
                  .sort((a, b) => b.id.localeCompare(a.id))
                  .map((e) => (
                    <tr key={e.id} className="border-b last:border-0">
                      <td className="w-[7rem] max-w-[7rem] truncate px-3 py-2 text-xs">
                        {e.item || "—"}
                      </td>
                      <td className="px-3 py-2 text-xs tabular-nums">
                        {e.date}
                        {entryTime(e.id) && (
                          <span className="ml-2 text-muted-foreground">{entryTime(e.id)}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right text-xs tabular-nums text-muted-foreground">
                        {(e.size / 1024).toFixed(1)}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => void restoreEntry(e.id)}
                            className="rounded-md border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                          >
                            Restore
                          </button>
                          <button
                            type="button"
                            onClick={() => void purgeEntry(e.id)}
                            className="rounded-md border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )
        ) : sortedEntries.length === 0 ? (
          <p className="px-3 py-4 text-sm text-muted-foreground">No entries yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-xs text-muted-foreground">
                <th className="px-3 py-2 text-left">Item</th>
                <th className="px-3 py-2 text-left">Date</th>
                <th className="px-3 py-2 text-right">Size (KB)</th>
              </tr>
            </thead>
            <tbody>
              {sortedEntries.map((e) => (
                <tr
                  key={e.id}
                  onClick={() => void loadEntry(e.id)}
                  className={cn(
                    "group cursor-pointer border-b last:border-0 text-xs transition-colors",
                    selected === e.id
                      ? "bg-accent font-medium text-accent-foreground"
                      : "hover:bg-accent/50",
                  )}
                >
                  <td className="max-w-[7rem] truncate px-3 py-2">
                    {e.item || "—"}
                  </td>
                  <td className="truncate px-3 py-2 tabular-nums text-muted-foreground">
                    {e.date}
                    {entryTime(e.id) && (
                      <span className="ml-1">{entryTime(e.id)}</span>
                    )}
                  </td>
                  <td className="relative px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {(e.size / 1024).toFixed(1)}
                    <button
                      type="button"
                      onClick={(ev) => { ev.stopPropagation(); void deleteEntry(e.id) }}
                      aria-label={`Delete entry ${e.id}`}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-destructive focus:bg-accent focus:text-destructive focus:opacity-100 group-hover:opacity-100"
                    >
                      <TrashIcon />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {panelOpen && (
          <ResizeHandle
            onPointerDown={startResize}
            ariaLabel="Resize journal list"
          />
        )}
      </div>

      {/* Right: side panel */}
      {panelOpen && (
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Panel header */}
          <div className="flex items-center justify-between border-b px-4 py-2">
            <div className="flex gap-3 text-xs text-muted-foreground">
              {composing && !selected ? (
                <span className="font-medium">New entry</span>
              ) : (
                <>
                  <span>
                    {selectedMeta?.date ?? selected}
                    {selected && entryTime(selected) && ` ${entryTime(selected)}`}
                  </span>
                  {selectedMeta && (
                    <span>{(selectedMeta.size / 1024).toFixed(1)} KB</span>
                  )}
                </>
              )}
            </div>
            <button
              onClick={closePanel}
              aria-label="Close panel"
              className={HEADER_BTN}
            >
              <CloseIcon />
            </button>
          </div>

          {/* Panel body */}
          <div className="flex-1 overflow-y-auto px-4 py-4">
            <div className="flex flex-col gap-6">
              {/* Brainstorm with Claude */}
              <section className="flex flex-col gap-3 rounded-lg border bg-card p-4">
                {turns.length > 0 && (
                  <div className="flex flex-col gap-4">
                    {turns.map((turn, i) => (
                      <div key={i} className="flex flex-col gap-2">
                        <div className="self-end rounded-2xl rounded-br-sm bg-muted px-4 py-2 text-sm text-foreground">
                          {turn.question}
                        </div>
                        <div className={cn(PROSE, "self-start rounded-2xl rounded-bl-sm border bg-background px-4 py-2")}>
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

                <div className="flex flex-col gap-2">
                  <textarea
                    ref={brainstormRef}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                        e.preventDefault()
                        void brainstorm()
                      }
                    }}
                    placeholder="e.g. What should I focus on next based on this week?"
                    rows={3}
                    className={`w-full resize-y rounded-md border bg-background p-3 text-sm${isBrainstormDragging ? " ring-2 ring-primary" : ""}`}
                  />
                  <ImageAttachArea
                    attachedImage={brainstormImage}
                    onAttach={setBrainstormImage}
                    onRemove={() => setBrainstormImage(null)}
                    isDragging={isBrainstormDragging}
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
        </div>
      )}
    </div>
  )
}
