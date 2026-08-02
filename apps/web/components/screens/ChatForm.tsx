"use client"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { ChatComposer } from "@/components/chat/ChatComposer"
import { ChatMessageList } from "@/components/chat/ChatMessageList"
import { SessionExpiredCard } from "@/components/SessionExpiredCard"
import { useChatJobState } from "@/lib/chatJobStore"
import { useChatState, type ChatMessage } from "@/lib/chatStore"
import { useChatHistoryNavigation } from "@/lib/hooks/useChatHistoryNavigation"
import { useDraftPersistence } from "@/lib/hooks/useDraftPersistence"
import { useNotionCredentials } from "@/lib/hooks/useNotionCredentials"
import { useNotionSave } from "@/lib/hooks/useNotionSave"
import { useSpeechRecognition } from "@/lib/hooks/useSpeechRecognition"
import { formatLocalDate } from "@/lib/utils"

function today(): string {
  return formatLocalDate()
}

interface ChatFormProps {
  /**
   * Fill the host's height (scrolling log + composer pinned to the bottom)
   * instead of stacking at natural height. The host must give this component a
   * definite height for it to have any effect.
   */
  fill?: boolean
  /**
   * Called with the appended markdown path each time an answer lands in the
   * local briefing mirror, so a host rendering that file can refresh it.
   */
  onLocalSave?: (path: string) => void
}

export function ChatForm({ fill = false, onLocalSave }: ChatFormProps = {}) {
  const { messages: committedMessages, setMessages, hydrated } = useChatState()
  const chatJob = useChatJobState()
  const { draft: input, setDraft: setInput } = useDraftPersistence({
    storageKey: "ai-agent:chat-draft:v1",
  })
  const [retrying, setRetrying] = useState(false)
  const [searchHistory, setSearchHistory] = useState(false)
  const { notionReady } = useNotionCredentials()
  const { supportsMic, listening, toggle: toggleMic } = useSpeechRecognition({
    onTranscript: setInput,
  })
  // Notion save targets committed turns only — never the in-flight one. It
  // fires automatically per completed answer when Notion is configured; the
  // button stays as the manual retry path after a failure.
  const { notionState, saveToNotion } = useNotionSave({
    messages: committedMessages,
    autoSave: notionReady,
    hydrated,
    onLocalSave,
  })

  // Latch to enforce "retry at most once per user send" across status flips.
  // Reset each time the user invokes send() so the next turn gets its own
  // budget. NOT persisted: a reload mid-retry just spends a fresh budget,
  // which we consider acceptable since stale_session is rare.
  const retriedRef = useRef(false)

  // Up/Down history of prior user questions (Issue #117). The chatStore
  // history is the durable source of truth.
  const userHistory = useMemo(
    () =>
      committedMessages.filter((m) => m.role === "user").map((m) => m.content),
    [committedMessages],
  )
  const busy = chatJob.isBackgrounded
  const onHistoryKeyDown = useChatHistoryNavigation({
    history: userHistory,
    setInput,
    busy,
  })

  // The user/assistant pair currently being streamed (or null when idle).
  // Appended onto the committed list so ChatMessageList can render the
  // in-flight turn without knowing the store split.
  const inFlightTurn = useMemo<ChatMessage[] | null>(() => {
    if (!chatJob.jobId && chatJob.status !== "pending") return null
    if (!chatJob.question) return null
    return [
      { role: "user", content: chatJob.question },
      {
        role: "assistant",
        content: chatJob.assistantContent,
        error: chatJob.error,
      },
    ]
  }, [
    chatJob.jobId,
    chatJob.status,
    chatJob.question,
    chatJob.assistantContent,
    chatJob.error,
  ])
  const displayMessages = useMemo(
    () =>
      inFlightTurn ? [...committedMessages, ...inFlightTurn] : committedMessages,
    [committedMessages, inFlightTurn],
  )

  const send = useCallback((imagePath?: string) => {
    const question = input.trim()
    if (!question || busy) return
    setInput("")
    setRetrying(false)
    retriedRef.current = false
    void chatJob.startJob({
      question,
      date: today(),
      ...(imagePath ? { image_path: imagePath } : {}),
      ...(searchHistory ? { search_history: true } : {}),
    })
  }, [busy, chatJob, input, searchHistory, setInput])

  // Cancel: terminate the backend job, commit the partial answer as a
  // cancelled turn to chat history, restore the question into the textarea
  // for re-edit. We don't await DELETE — the user-facing UX should switch
  // immediately, the backend cleanup is best-effort.
  const cancel = useCallback(() => {
    if (!busy) return
    const jobId = chatJob.jobId
    const question = chatJob.question
    const partial = chatJob.assistantContent
    if (jobId) {
      void fetch(`/api/chat/${jobId}`, { method: "DELETE", cache: "no-store" })
    }
    if (question) {
      setMessages((prev) => [
        ...prev,
        { role: "user", content: question },
        { role: "assistant", content: partial, cancelled: true },
      ])
      setInput(question)
    }
    chatJob.reset()
  }, [busy, chatJob, setInput, setMessages])

  // Watch the job for terminal transitions: retry once on stale_session,
  // otherwise commit the in-flight turn to chat history and reset the store.
  // The store handles session expiry (renders the SessionExpiredCard guard
  // below) so this effect skips that path.
  useEffect(() => {
    if (chatJob.sessionExpired) return
    if (chatJob.status !== "done" && chatJob.status !== "failed") return
    if (!chatJob.question) return

    if (chatJob.staleSession && !retriedRef.current) {
      retriedRef.current = true
      const { question, date, searchHistory: retrySearchHistory } = chatJob
      setRetrying(true)
      chatJob.reset()
      void chatJob
        .startJob({
          question,
          date,
          ...(retrySearchHistory ? { search_history: true } : {}),
        })
        .finally(() => {
          setRetrying(false)
        })
      return
    }

    const userMsg: ChatMessage = { role: "user", content: chatJob.question }
    const assistantMsg: ChatMessage = {
      role: "assistant",
      content: chatJob.assistantContent,
      error: chatJob.error,
    }
    setMessages((prev) => [...prev, userMsg, assistantMsg])
    chatJob.reset()
    // chatJob is read inside but excluded from deps — its identity flips on
    // every render via the wrapping useMemo, and we only want this effect to
    // fire on terminal status transitions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatJob.status, chatJob.sessionExpired])

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

  if (chatJob.sessionExpired) {
    return <SessionExpiredCard />
  }

  return (
    <div className={fill ? "flex h-full min-h-0 flex-col gap-4" : "space-y-4"}>
      <ChatMessageList
        messages={displayMessages}
        busy={busy}
        retrying={retrying}
        notionReady={notionReady}
        notionState={notionState}
        onNotionSave={(idx) => void saveToNotion(idx)}
        fill={fill}
      />
      <ChatComposer
        input={input}
        setInput={setInput}
        busy={busy}
        supportsMic={supportsMic}
        listening={listening}
        onToggleMic={toggleMic}
        onSend={send}
        onCancel={cancel}
        onHistoryKeyDown={onHistoryKeyDown}
        searchHistory={searchHistory}
        onToggleSearchHistory={setSearchHistory}
      />
    </div>
  )
}
