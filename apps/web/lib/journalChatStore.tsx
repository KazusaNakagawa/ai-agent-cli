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

/**
 * Committed Journal brainstorm turns + the entry they're bound to. Split
 * from the in-flight job (journalChatJobStore) the same way chatStore
 * splits committed messages from chatJobStore's in-flight job — completed
 * turns live here so a job reset (after save) never re-shows them.
 */

export type JournalTurn = { question: string; answer: string }

export type JournalChatStateContextValue = {
  turns: JournalTurn[]
  entryId: string | null
  addTurn: (turn: JournalTurn) => void
  setEntryId: (id: string | null) => void
  reset: () => void
}

export const JOURNAL_CHAT_HISTORY_STORAGE_KEY = "ai-agent:journal-chat-history:v1"
const MAX_TURNS = 50

type Persisted = { turns: JournalTurn[]; entryId: string | null }

function isJournalTurn(value: unknown): value is JournalTurn {
  if (typeof value !== "object" || value === null) return false
  const t = value as Partial<JournalTurn>
  return typeof t.question === "string" && typeof t.answer === "string"
}

function capTurns(turns: JournalTurn[]): JournalTurn[] {
  if (turns.length <= MAX_TURNS) return turns
  return turns.slice(turns.length - MAX_TURNS)
}

function loadPersisted(): Persisted {
  if (typeof window === "undefined") return { turns: [], entryId: null }
  try {
    const raw = window.sessionStorage.getItem(JOURNAL_CHAT_HISTORY_STORAGE_KEY)
    if (!raw) return { turns: [], entryId: null }
    const parsed = JSON.parse(raw) as Partial<Persisted>
    const turns = Array.isArray(parsed.turns)
      ? capTurns(parsed.turns.filter(isJournalTurn))
      : []
    const entryId = typeof parsed.entryId === "string" ? parsed.entryId : null
    return { turns, entryId }
  } catch {
    return { turns: [], entryId: null }
  }
}

function persist(state: Persisted): void {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(JOURNAL_CHAT_HISTORY_STORAGE_KEY, JSON.stringify(state))
  } catch {
    // quota / unavailable — state remains in memory for the tab
  }
}

function clearPersisted(): void {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.removeItem(JOURNAL_CHAT_HISTORY_STORAGE_KEY)
  } catch {
    // ignore
  }
}

const JournalChatStateContext = createContext<JournalChatStateContextValue | null>(null)

export function JournalChatStateProvider({ children }: { children: ReactNode }) {
  const [turns, setTurns] = useState<JournalTurn[]>([])
  const [entryId, setEntryIdState] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    const persisted = loadPersisted()
    setTurns(persisted.turns)
    setEntryIdState(persisted.entryId)
    setHydrated(true)
  }, [])

  useEffect(() => {
    if (!hydrated) return
    if (turns.length === 0 && entryId === null) {
      clearPersisted()
    } else {
      persist({ turns, entryId })
    }
  }, [turns, entryId, hydrated])

  const addTurn = useCallback((turn: JournalTurn) => {
    setTurns((prev) => capTurns([...prev, turn]))
  }, [])

  const setEntryId = useCallback((id: string | null) => {
    setEntryIdState(id)
  }, [])

  const reset = useCallback(() => {
    setTurns([])
    setEntryIdState(null)
    clearPersisted()
  }, [])

  const value = useMemo<JournalChatStateContextValue>(
    () => ({ turns, entryId, addTurn, setEntryId, reset }),
    [turns, entryId, addTurn, setEntryId, reset],
  )

  return (
    <JournalChatStateContext.Provider value={value}>
      {children}
    </JournalChatStateContext.Provider>
  )
}

export function useJournalChatState(): JournalChatStateContextValue {
  const ctx = useContext(JournalChatStateContext)
  if (!ctx) {
    throw new Error("useJournalChatState must be used inside <JournalChatStateProvider>")
  }
  return ctx
}
