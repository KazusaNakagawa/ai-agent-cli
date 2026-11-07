"use client"
import { useCallback, useEffect, useRef, useState } from "react"

import { CloseIcon } from "@/components/briefing/icons"
import { ChatComposer } from "@/components/chat/ChatComposer"
import { JournalTurn } from "@/components/journal/JournalTurn"
import { MarkdownView } from "@/components/ui/MarkdownView"
import { useJournalChatJobState } from "@/lib/journalChatJobStore"
import { useJournalChatState } from "@/lib/journalChatStore"
import { useJournalNav } from "@/lib/journalNavStore"
import { parseQaTranscript } from "@/lib/journalQa"
import { useSpeechRecognition } from "@/lib/hooks/useSpeechRecognition"

const HEADER_BTN =
  "rounded p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"

/** Extract HH:MM:SS from an entry id (YYYY-MM-DD_HHMMSS), or null for legacy day ids. */
function entryTime(id: string): string | null {
  const m = id.match(/^\d{4}-\d{2}-\d{2}_(\d{2})(\d{2})(\d{2})/)
  return m ? `${m[1]}:${m[2]}:${m[3]}` : null
}

/** Drop the leading `# Journal YYYY-MM-DD` heading — the panel header already shows the date. */
function stripTitleHeading(md: string): string {
  return md.replace(/^\s*# [^\n]*\n+/, "")
}

/** A saved entry: chat bubbles when it holds role-labelled Q&A, plain Markdown otherwise. */
function EntryBody({ md }: { md: string }) {
  const body = stripTitleHeading(md)
  const transcript = parseQaTranscript(body)
  if (!transcript) return <MarkdownView content={body} breaks />
  return (
    <div className="flex flex-col gap-6">
      {transcript.preamble && <MarkdownView content={transcript.preamble} breaks />}
      {transcript.turns.map((turn, i) => (
        <JournalTurn key={i} question={turn.question} answer={turn.answer} />
      ))}
    </div>
  )
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

  const [question, setQuestion] = useState("")
  const { supportsMic, listening, toggle: toggleMic } = useSpeechRecognition({
    onTranscript: setQuestion,
  })
  const journalChat = useJournalChatState()
  const job = useJournalChatJobState()
  const brainstorming = job.status === "pending" || job.status === "running"
  const chatError = job.error
  const brainstormEpoch = useRef(0)

  // Called by ChatComposer, which holds the images and the send guards (empty
  // input, uploads still in flight).
  const brainstorm = useCallback(async (imagePaths: string[]) => {
    const q = question.trim()
    if (!q || brainstorming) return
    setQuestion("")
    brainstormEpoch.current = viewEpoch.current
    await job.startJob({
      question: q,
      // The composer clears its images on send, including when the job is later
      // cancelled or fails — re-attaching images to a retyped question is a
      // minor inconvenience compared to threading the outcome back.
      imagePaths,
      targetEntryId: journalChat.entryId,
    })
    // viewEpoch is a ref (stable identity) read only for its .current value at
    // call time, so it's intentionally omitted from the dependency array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question, brainstorming, job, journalChat.entryId])

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

  const title = trashPreview
    ? trashMeta?.item || trashPreview
    : composing && !selected
      ? null
      : selectedMeta?.item || selected

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden rounded-lg border bg-background">
      {/* Panel header */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {!trashPreview && !(composing && !selected) && <span>Journal</span>}
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

      {/* Panel title */}
      {title && (
        <div className="border-b px-4 py-3">
          <h2 className="truncate text-sm font-semibold" data-testid="journal-panel-title">
            {title}
          </h2>
        </div>
      )}

      {/* Panel body: the entry and the brainstorm turns scroll; the composer
          below stays pinned to the bottom of the panel. */}
      <div className="scrollbar-slim flex-1 overflow-y-auto px-4 py-4 pr-6">
        {trashPreview ? (
          /* Read-only preview of a trashed entry — no brainstorm here. */
          trashContent ? (
            <EntryBody md={trashContent} />
          ) : (
            <p className="text-sm text-muted-foreground">Loading…</p>
          )
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
            {/* Entry content (read view; hidden while composing a new entry) */}
            {selected && content && (
              <div data-testid="journal-content">
                <EntryBody md={content} />
              </div>
            )}

            {displayTurns.length > 0 && (
              <div className="flex flex-col gap-6">
                {displayTurns.map((turn, i) => (
                  <JournalTurn key={i} question={turn.question} answer={turn.answer || null} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Brainstorm with Claude */}
      {!trashPreview && (
        <div className="border-t px-4 pb-4 pt-3">
          <ChatComposer
            input={question}
            setInput={setQuestion}
            busy={brainstorming}
            supportsMic={supportsMic}
            listening={listening}
            onToggleMic={toggleMic}
            onSend={(imagePaths) => void brainstorm(imagePaths)}
            onCancel={cancelBrainstorm}
            placeholder="e.g. What should I focus on next based on this week?"
            sendLabel="Brainstorm"
            cancelLabel="Stop"
          />
          {chatError && (
            <p className="mx-auto max-w-3xl px-3 pt-2 text-sm text-destructive">{chatError}</p>
          )}
        </div>
      )}
    </div>
  )
}
