import { render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import {
  ChatStateProvider,
  type ChatMessage,
  useChatState,
} from "@/lib/chatStore"

const STORAGE_KEY = "ai-agent:chat-history:v1"

// Renders the messages array as one <div data-testid="msg-N"> per entry so
// tests can assert on hydrated content without depending on ChatForm's chrome.
function MessageProbe() {
  const { messages, setMessages, reset } = useChatState()
  return (
    <div>
      <span data-testid="count">{messages.length}</span>
      {messages.map((m, i) => (
        <div key={i} data-testid={`msg-${i}`} data-role={m.role}>
          {m.content}
        </div>
      ))}
      <button
        data-testid="append-pair"
        onClick={() =>
          setMessages((prev) => [
            ...prev,
            { role: "user", content: `u${prev.length}` },
            { role: "assistant", content: `a${prev.length}` },
          ])
        }
      />
      <button
        data-testid="grow-last"
        onClick={() =>
          setMessages((prev) => {
            const copy = [...prev]
            const last = copy[copy.length - 1]
            if (last && last.role === "assistant") {
              copy[copy.length - 1] = { ...last, content: last.content + "x" }
            }
            return copy
          })
        }
      />
      <button data-testid="reset" onClick={reset} />
    </div>
  )
}

describe("ChatStateProvider — sessionStorage persistence", () => {
  beforeEach(() => {
    sessionStorage.clear()
  })
  afterEach(() => {
    sessionStorage.clear()
  })

  it("hydrates messages from sessionStorage on mount (AC: tab-switch restores conversation)", async () => {
    const stored: ChatMessage[] = [
      { role: "user", content: "what's new?" },
      { role: "assistant", content: "today: …" },
    ]
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(stored))

    render(
      <ChatStateProvider>
        <MessageProbe />
      </ChatStateProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("count")).toHaveTextContent("2")
    })
    expect(screen.getByTestId("msg-0")).toHaveTextContent("what's new?")
    expect(screen.getByTestId("msg-1")).toHaveTextContent("today: …")
  })

  it("starts empty when nothing is stored", async () => {
    render(
      <ChatStateProvider>
        <MessageProbe />
      </ChatStateProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId("count")).toHaveTextContent("0")
    })
  })

  it("ignores malformed sessionStorage payloads instead of throwing", async () => {
    sessionStorage.setItem(STORAGE_KEY, "{not-json")

    render(
      <ChatStateProvider>
        <MessageProbe />
      </ChatStateProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId("count")).toHaveTextContent("0")
    })
  })

  it("filters out entries that don't look like ChatMessage on hydration", async () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        { role: "user", content: "kept" },
        { role: "assistant", content: "kept too", error: null },
        { role: "assistant", content: "kept three", error: "stream error" },
        { role: "bogus", content: "dropped" },
        { role: "assistant" }, // missing content
        { role: "assistant", content: "bad error", error: 123 }, // non-string error
        "string entry",
        null,
      ]),
    )

    render(
      <ChatStateProvider>
        <MessageProbe />
      </ChatStateProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId("count")).toHaveTextContent("3")
    })
    expect(screen.getByTestId("msg-0")).toHaveTextContent("kept")
    expect(screen.getByTestId("msg-1")).toHaveTextContent("kept too")
    expect(screen.getByTestId("msg-2")).toHaveTextContent("kept three")
  })

  it("enforces a FIFO cap of 50 messages — the oldest drops when the 51st arrives", async () => {
    // Seed 49 messages; one click of "append-pair" pushes the count to 51,
    // which must be capped back to 50 with the oldest entry removed.
    const seeded: ChatMessage[] = Array.from({ length: 49 }, (_, i) => ({
      role: i % 2 === 0 ? "user" : "assistant",
      content: `seed-${i}`,
    }))
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(seeded))

    render(
      <ChatStateProvider>
        <MessageProbe />
      </ChatStateProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("count")).toHaveTextContent("49")
    })
    screen.getByTestId("append-pair").click()
    await waitFor(() => {
      expect(screen.getByTestId("count")).toHaveTextContent("50")
    })
    // Oldest seeded entry (seed-0) dropped — first surviving is seed-1.
    expect(screen.getByTestId("msg-0")).toHaveTextContent("seed-1")
    // Persisted snapshot matches the in-memory cap.
    const persisted = JSON.parse(
      sessionStorage.getItem(STORAGE_KEY) ?? "[]",
    ) as ChatMessage[]
    expect(persisted).toHaveLength(50)
    expect(persisted[0].content).toBe("seed-1")
  })

  it("round-trips a partial assistant message (mid-stream content) through storage", async () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        { role: "user", content: "q" },
        { role: "assistant", content: "partial answer so fa" }, // mid-stream
      ]),
    )

    const { unmount } = render(
      <ChatStateProvider>
        <MessageProbe />
      </ChatStateProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("msg-1")).toHaveTextContent(
        "partial answer so fa",
      )
    })

    // Simulate another streaming chunk arriving while still mounted, then
    // remount (tab-switch) and verify the appended content survives.
    screen.getByTestId("grow-last").click()
    await waitFor(() => {
      expect(screen.getByTestId("msg-1")).toHaveTextContent(
        "partial answer so fax",
      )
    })
    unmount()

    render(
      <ChatStateProvider>
        <MessageProbe />
      </ChatStateProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId("msg-1")).toHaveTextContent(
        "partial answer so fax",
      )
    })
  })

  it("reset() clears messages and removes the sessionStorage entry", async () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([{ role: "user", content: "hi" }]),
    )

    render(
      <ChatStateProvider>
        <MessageProbe />
      </ChatStateProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("count")).toHaveTextContent("1")
    })
    screen.getByTestId("reset").click()
    await waitFor(() => {
      expect(screen.getByTestId("count")).toHaveTextContent("0")
    })
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})
