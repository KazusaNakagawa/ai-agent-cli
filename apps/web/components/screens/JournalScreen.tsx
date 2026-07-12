"use client"
import { useCallback, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { CloseIcon } from "@/components/briefing/icons"
import { ImageAttachArea } from "@/components/ui/ImageAttachArea"
import { LoadingDots } from "@/components/ui/loading-dots"
import { useImageDrop } from "@/lib/hooks/useImageDrop"
import { insertAtCursor } from "@/lib/insertAtCursor"
import { useJournalChatJobState } from "@/lib/journalChatJobStore"
import { useJournalChatState } from "@/lib/journalChatStore"
import { useJournalNav } from "@/lib/journalNavStore"
import { useSpeechRecognition } from "@/lib/hooks/useSpeechRecognition"
import type { ImageAttachment } from "@/lib/types/image"
import { cn } from "@/lib/utils"

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
  const {
    selected,
    composing,
    trashPreview,
    content,
    trashContent,
    panelOpen,
    selectedMeta,
    trashMeta,
    viewEpoch,
    closePanel,
    restoreEntry,
    purgeEntry,
  } = useJournalNav()

  const brainstormRef = useRef<HTMLTextAreaElement>(null)
  const [brainstormImage, setBrainstormImage] = useState<ImageAttachment | null>(null)
  const { isDragging: isBrainstormDragging } = useImageDrop(brainstormRef, setBrainstormImage)

  const [question, setQuestion] = useState("")
  const { supportsMic, listening, toggle: toggleMic } = useSpeechRecognition({
    onTranscript: setQuestion,
  })
  const journalChat = useJournalChatState()
  const job = useJournalChatJobState()
  const brainstorming = job.status === "pending" || job.status === "running"
  const chatError = job.error
  const brainstormEpoch = useRef(0)

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
    // viewEpoch is a ref (stable identity) read only for its .current value at
    // call time, so it's intentionally omitted from the dependency array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  if (!panelOpen) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Select an entry or click + New to get started.
      </div>
    )
  }

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden">
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
                          <LoadingDots label="考え中" data-testid="journal-chat-thinking" />
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
                    {brainstorming ? (
                      <LoadingDots label="考え中" className="text-primary-foreground" />
                    ) : (
                      "Brainstorm"
                    )}
                  </button>
                  {supportsMic && (
                    <button
                      type="button"
                      onClick={() => toggleMic(question)}
                      data-testid="mic-button"
                      aria-label={listening ? "音声入力停止" : "音声入力開始"}
                      aria-pressed={listening}
                      title={listening ? "音声入力停止" : "音声入力開始 (ja-JP)"}
                      className={cn(
                        "rounded-md border px-3 py-2 text-sm transition-colors",
                        listening
                          ? "border-destructive bg-destructive text-destructive-foreground"
                          : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                      )}
                    >
                      {listening ? "🛑" : "🎤"}
                    </button>
                  )}
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
                {!supportsMic && (
                  <p
                    className="text-xs text-muted-foreground"
                    data-testid="mic-unsupported"
                  >
                    Voice input is unavailable in this browser (Chrome / Edge supported).
                  </p>
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
