"use client"
import { useEffect, useRef } from "react"

import { formatQaBlock } from "@/lib/journalQa"
import { useJournalChatJobState } from "@/lib/journalChatJobStore"
import { useJournalChatState } from "@/lib/journalChatStore"

/**
 * Always-mounted glue between the Journal brainstorm job and its committed
 * turn history. Runs at the (main) layout level (not inside JournalScreen)
 * so a finished job is saved and committed even while the user has
 * navigated to another page. Renders nothing.
 */
export function JournalChatBridge(): null {
  const job = useJournalChatJobState()
  const journalChat = useJournalChatState()
  // Guards against the completion effect re-running for the same job (e.g.
  // a StrictMode double-invoke or an unrelated re-render while the async
  // save is in flight) — without this a slow save could fire twice.
  const processing = useRef(new Set<string>())

  const { status, jobId, question, assistantContent, targetEntryId, setError, reset } = job
  const { addTurn, setEntryId } = journalChat

  useEffect(() => {
    if (status !== "done" || !jobId) return
    if (processing.current.has(jobId)) return
    processing.current.add(jobId)

    void (async () => {
      const qaBlock = formatQaBlock(question, assistantContent)
      let saveRes: Response
      try {
        saveRes = targetEntryId
          ? await fetch(`/api/journal/${targetEntryId}`, {
              method: "PATCH",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ content: qaBlock }),
            })
          : await fetch("/api/journal", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ content: qaBlock, item: question.slice(0, 20) }),
            })
      } catch (e) {
        setError(e instanceof Error ? e.message : "Auto-save network error")
        processing.current.delete(jobId)
        return
      }
      if (!saveRes.ok) {
        const body = await saveRes.text().catch(() => "")
        setError(`Auto-save failed (HTTP ${saveRes.status}): ${body}`)
        processing.current.delete(jobId)
        return
      }
      let entryId = targetEntryId
      if (!entryId) {
        const saved = (await saveRes.json()) as { id: string }
        entryId = saved.id
      }
      addTurn({ question, answer: assistantContent })
      setEntryId(entryId)
      reset()
      processing.current.delete(jobId)
    })()
  }, [status, jobId, question, assistantContent, targetEntryId, setError, reset, addTurn, setEntryId])

  return null
}
