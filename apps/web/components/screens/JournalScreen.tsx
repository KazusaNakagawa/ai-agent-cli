"use client"
import { useCallback, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { CloseIcon, TrashIcon } from "@/components/briefing/icons"
import { ResizeHandle } from "@/components/ResizeHandle"
import { ImageAttachArea } from "@/components/ui/ImageAttachArea"
import { useImageDrop } from "@/lib/hooks/useImageDrop"
import { insertAtCursor } from "@/lib/insertAtCursor"
import { useJournalChatJobState } from "@/lib/journalChatJobStore"
import { useJournalChatState } from "@/lib/journalChatStore"
import { useResizable } from "@/lib/hooks/useResizable"
import type { ImageAttachment } from "@/lib/types/image"
import { cn } from "@/lib/utils"

type JournalEntry = { id: string; date: string; size: number; item: string; notion_url: string }

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
  // Read-only preview of a trashed entry (so the user can inspect before
  // restoring or permanently deleting it).
  const [trashPreview, setTrashPreview] = useState<string | null>(null)
  const [trashContent, setTrashContent] = useState("")
  const trashReqSeq = useRef(0)

  const [question, setQuestion] = useState("")
  const journalChat = useJournalChatState()
  const job = useJournalChatJobState()
  const brainstorming = job.status === "pending" || job.status === "running"
  const chatError = job.error
  // Bumped on every entry switch/compose/trash toggle so a pending job
  // started under a previous view doesn't reappear if the id-matching
  // heuristic below can't distinguish "same view" from "new view" (e.g. two
  // successive new-entry sessions both have targetEntryId=null). Reset to 0
  // on every JournalScreen mount, which is exactly the state a fresh
  // navigation back to Journal starts from — so a job started before
  // navigating away still shows on return.
  const viewEpoch = useRef(0)
  const brainstormEpoch = useRef(0)

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
    viewEpoch.current += 1
    // Bind the brainstorm session to this entry so subsequent turns append here.
    journalChat.reset()
    journalChat.setEntryId(entryId)
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
  }, [journalChat])

  const loadTrashEntry = useCallback(async (entryId: string) => {
    const seq = ++trashReqSeq.current
    setTrashPreview(entryId)
    setTrashContent("")
    let res: Response
    try {
      res = await fetch(`/api/journal/trash/${entryId}`, { cache: "no-store" })
    } catch {
      return
    }
    if (seq !== trashReqSeq.current) return
    if (!res.ok) return
    const data = (await res.json()) as { content: string }
    if (seq !== trashReqSeq.current) return
    setTrashContent(data.content)
  }, [])

  useEffect(() => {
    void loadDates()
  }, [loadDates])

  const closePanel = () => {
    setSelected(null)
    setComposing(false)
    setTrashPreview(null)
    journalChat.setEntryId(null)
  }

  const startCompose = () => {
    setSelected(null)
    setTrashPreview(null)
    viewEpoch.current += 1
    journalChat.reset()
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
        setTrashPreview((cur) => (cur === entryId ? null : cur))
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
        setTrashPreview((cur) => (cur === entryId ? null : cur))
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
    // Switching views closes any open panel/preview so the two modes don't mix.
    setSelected(null)
    setComposing(false)
    setTrashPreview(null)
    viewEpoch.current += 1
    journalChat.reset()
    if (next) void loadTrash()
  }, [showTrash, loadTrash, journalChat])

  const brainstorm = useCallback(async () => {
    const q = question.trim()
    if (!q || brainstorming) return
    setQuestion("")
    brainstormEpoch.current = viewEpoch.current
    await job.startJob({
      question: q,
      imagePath: brainstormImage?.path ?? null,
      targetEntryId: journalChat.entryId,
    })
    // Cleared unconditionally (including on cancel/failure) — simpler than
    // threading the outcome back through startJob's return value, and
    // re-attaching an image to a retyped question is a minor inconvenience
    // compared to the state this replaces.
    setBrainstormImage(null)
  }, [question, brainstorming, brainstormImage, job, journalChat.entryId])

  // Abort the in-flight brainstorm and terminate the backend job — works
  // whether or not the backend job_id has arrived yet (journalChatJobStore
  // queues the cancel and fires the DELETE once it does).
  const cancelBrainstorm = useCallback(() => {
    if (job.status === "idle") return
    const q = job.question
    job.cancelJob()
    setQuestion(q)
  }, [job])

  // Esc cancels the in-flight brainstorm (matches Q&A ChatForm behavior).
  useEffect(() => {
    if (!brainstorming) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault()
        cancelBrainstorm()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [brainstorming, cancelBrainstorm])

  // The in-flight job only renders as a pending bubble while the view it
  // was started from is still current — matches the pre-refactor behavior
  // where switching entries/composing/trash cleared the visible transcript
  // even though the backend job kept running in the background.
  const showPendingTurn = job.jobId !== null && brainstormEpoch.current === viewEpoch.current
  const displayTurns = showPendingTurn
    ? [...journalChat.turns, { question: job.question, answer: job.assistantContent }]
    : journalChat.turns

  const sortedEntries = [...entries].sort((a, b) => b.id.localeCompare(a.id))
  const selectedMeta = sortedEntries.find((e) => e.id === selected)
  const trashMeta = trash.find((e) => e.id === trashPreview)
  const panelOpen = selected !== null || composing || trashPreview !== null

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
                    <tr
                      key={e.id}
                      tabIndex={0}
                      role="button"
                      aria-label={`Preview trashed entry ${e.item || e.id}`}
                      onClick={() => void loadTrashEntry(e.id)}
                      onKeyDown={(ev) => {
                        if (ev.key === "Enter" || ev.key === " ") {
                          ev.preventDefault()
                          void loadTrashEntry(e.id)
                        }
                      }}
                      className={cn(
                        "cursor-pointer border-b last:border-0 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                        trashPreview === e.id
                          ? "bg-accent font-medium text-accent-foreground"
                          : "hover:bg-accent/50",
                      )}
                    >
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
                            onClick={(ev) => { ev.stopPropagation(); void restoreEntry(e.id) }}
                            className="rounded-md border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                          >
                            Restore
                          </button>
                          <button
                            type="button"
                            onClick={(ev) => { ev.stopPropagation(); void purgeEntry(e.id) }}
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
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              {trashPreview ? (
                <>
                  <span className="font-medium text-destructive">Trash</span>
                  <span>
                    {trashMeta?.date ?? trashPreview}
                    {entryTime(trashPreview) && ` ${entryTime(trashPreview)}`}
                  </span>
                  {trashMeta && (
                    <span>{(trashMeta.size / 1024).toFixed(1)} KB</span>
                  )}
                </>
              ) : composing && !selected ? (
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
                  {selectedMeta?.notion_url ? (
                    <a
                      href={selectedMeta.notion_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 hover:underline dark:text-blue-400"
                    >
                      Synced to Notion ↗
                    </a>
                  ) : (
                    selectedMeta && (
                      <span title="Syncs automatically once NOTION_DATABASE_ID_JOURNAL is configured">
                        Not synced to Notion
                      </span>
                    )
                  )}
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              {trashPreview && (
                <>
                  <button
                    type="button"
                    onClick={() => void restoreEntry(trashPreview)}
                    className="rounded-md border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                  >
                    Restore
                  </button>
                  <button
                    type="button"
                    onClick={() => void purgeEntry(trashPreview)}
                    className="rounded-md border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
                  >
                    Delete
                  </button>
                </>
              )}
              <button
                onClick={closePanel}
                aria-label="Close panel"
                className={HEADER_BTN}
              >
                <CloseIcon />
              </button>
            </div>
          </div>

          {/* Panel body */}
          <div className="flex-1 overflow-y-auto px-4 py-4">
            {trashPreview ? (
              /* Read-only preview of a trashed entry — no brainstorm here. */
              trashContent ? (
                <div className={PROSE}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{trashContent}</ReactMarkdown>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Loading…</p>
              )
            ) : (
            <div className="flex flex-col gap-6">
              {/* Entry content (read view; hidden while composing a new entry) */}
              {selected && content && (
                <div className={PROSE}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                </div>
              )}

              {/* Brainstorm with Claude */}
              <section className="flex flex-col gap-3 rounded-lg border bg-card p-4">
                {displayTurns.length > 0 && (
                  <div className="flex flex-col gap-4">
                    {displayTurns.map((turn, i) => (
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
                    onInsertFile={(markdown) =>
                      setQuestion(insertAtCursor(brainstormRef.current, question, markdown))
                    }
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
                    {brainstorming && (
                      <button
                        type="button"
                        onClick={cancelBrainstorm}
                        className="rounded-md border px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
                        title="Cancel (Esc)"
                      >
                        Stop
                      </button>
                    )}
                    {chatError && <span className="text-sm text-destructive">{chatError}</span>}
                  </div>
                </div>
              </section>
            </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
