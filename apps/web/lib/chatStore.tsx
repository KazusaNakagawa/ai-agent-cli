"use client"
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

export type ChatMessage = {
  role: "user" | "assistant"
  content: string
  error?: string | null
}

export type ChatStateContextValue = {
  messages: ChatMessage[]
  setMessages: (
    updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[]),
  ) => void
  reset: () => void
}

// Bumped if the persisted shape changes incompatibly.
const STORAGE_KEY = "ai-agent:chat-history:v1"
// FIFO cap on individual messages — bounds sessionStorage growth against the
// ~5 MB browser quota while still covering long working sessions.
const MAX_MESSAGES = 50

function capMessages(messages: ChatMessage[]): ChatMessage[] {
  if (messages.length <= MAX_MESSAGES) return messages
  return messages.slice(messages.length - MAX_MESSAGES)
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (typeof value !== "object" || value === null) return false
  const m = value as Partial<ChatMessage>
  return (
    (m.role === "user" || m.role === "assistant") &&
    typeof m.content === "string" &&
    (m.error === undefined || m.error === null || typeof m.error === "string")
  )
}

function loadPersisted(): ChatMessage[] {
  if (typeof window === "undefined") return []
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return capMessages(parsed.filter(isChatMessage))
  } catch {
    return []
  }
}

function persist(messages: ChatMessage[]) {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages))
  } catch {
    // quota / unavailable — state remains in memory for the tab
  }
}

function clearPersisted() {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}

const ChatStateContext = createContext<ChatStateContextValue | null>(null)

export function ChatStateProvider({ children }: { children: ReactNode }) {
  // Render [] on first paint so SSR and the first client render agree
  // (sessionStorage is unavailable on the server). The hydrate effect below
  // promotes messages to whatever was persisted in this tab.
  const [messages, setMessagesState] = useState<ChatMessage[]>([])
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    setMessagesState(loadPersisted())
    setHydrated(true)
  }, [])

  useEffect(() => {
    if (!hydrated) return
    if (messages.length === 0) {
      clearPersisted()
    } else {
      persist(messages)
    }
  }, [messages, hydrated])

  const setMessages = useCallback<ChatStateContextValue["setMessages"]>(
    (updater) => {
      setMessagesState((prev) => {
        const next = typeof updater === "function" ? updater(prev) : updater
        return capMessages(next)
      })
    },
    [],
  )

  const reset = useCallback(() => {
    setMessagesState([])
    clearPersisted()
  }, [])

  const value = useMemo<ChatStateContextValue>(
    () => ({ messages, setMessages, reset }),
    [messages, setMessages, reset],
  )

  return (
    <ChatStateContext.Provider value={value}>
      {children}
    </ChatStateContext.Provider>
  )
}

export function useChatState(): ChatStateContextValue {
  const ctx = useContext(ChatStateContext)
  if (!ctx) {
    throw new Error("useChatState must be used inside <ChatStateProvider>")
  }
  return ctx
}
