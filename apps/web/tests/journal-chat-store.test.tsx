import { act, renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import {
  JOURNAL_CHAT_HISTORY_STORAGE_KEY as STORAGE_KEY,
  JournalChatStateProvider,
  useJournalChatState,
} from "@/lib/journalChatStore"

function wrapper({ children }: { children: ReactNode }) {
  return <JournalChatStateProvider>{children}</JournalChatStateProvider>
}

describe("journalChatStore", () => {
  beforeEach(() => window.sessionStorage.clear())
  afterEach(() => window.sessionStorage.clear())

  it("starts empty, appends turns, and persists them", async () => {
    const { result } = renderHook(() => useJournalChatState(), { wrapper })
    expect(result.current.turns).toEqual([])
    expect(result.current.entryId).toBeNull()

    act(() => {
      result.current.addTurn({ question: "Q1", answer: "A1" })
      result.current.setEntryId("entry-1")
    })

    expect(result.current.turns).toEqual([{ question: "Q1", answer: "A1" }])
    expect(result.current.entryId).toBe("entry-1")
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!)).toEqual({
      turns: [{ question: "Q1", answer: "A1" }],
      entryId: "entry-1",
    })
  })

  it("rehydrates persisted turns on a fresh mount", () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ turns: [{ question: "Q", answer: "A" }], entryId: "e1" }),
    )
    const { result } = renderHook(() => useJournalChatState(), { wrapper })
    expect(result.current.turns).toEqual([{ question: "Q", answer: "A" }])
    expect(result.current.entryId).toBe("e1")
  })

  it("reset clears turns, entryId, and storage", () => {
    const { result } = renderHook(() => useJournalChatState(), { wrapper })
    act(() => {
      result.current.addTurn({ question: "Q", answer: "A" })
      result.current.setEntryId("e1")
    })
    act(() => result.current.reset())
    expect(result.current.turns).toEqual([])
    expect(result.current.entryId).toBeNull()
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})
