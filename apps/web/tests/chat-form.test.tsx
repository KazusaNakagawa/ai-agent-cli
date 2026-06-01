import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ChatForm } from "@/components/screens/ChatForm"

type SSEPart = { event?: string; data: string }

// Build a Response whose body is a ReadableStream of well-formed SSE bytes.
function sseResponse(parts: SSEPart[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const p of parts) {
        let chunk = ""
        if (p.event) chunk += `event: ${p.event}\n`
        for (const line of p.data.split("\n")) chunk += `data: ${line}\n`
        chunk += "\n"
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
  return new Response(stream, { status: 200 })
}

describe("ChatForm", () => {
  const fetchMock = vi.fn()
  const DRAFT_KEY = "ai-agent:chat-draft:v1"

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
    window.sessionStorage.clear()
    // Default: no SpeechRecognition (mimics Firefox / unsupported browsers).
    delete (window as unknown as { SpeechRecognition?: unknown })
      .SpeechRecognition
    delete (window as unknown as { webkitSpeechRecognition?: unknown })
      .webkitSpeechRecognition
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("renders the empty state and a disabled send button", () => {
    render(<ChatForm />)
    expect(screen.getByTestId("chat-input")).toBeInTheDocument()
    expect(screen.getByTestId("send-button")).toBeDisabled()
  })

  it("enables send once the input is non-empty", async () => {
    const user = userEvent.setup()
    render(<ChatForm />)
    await user.type(screen.getByTestId("chat-input"), "hi")
    expect(screen.getByTestId("send-button")).not.toBeDisabled()
  })

  it("POSTs today's date + question and streams assistant output", async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse([{ data: "hello" }, { data: "world" }]),
    )
    const user = userEvent.setup()
    render(<ChatForm />)
    await user.type(screen.getByTestId("chat-input"), "what's new?")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      const assistant = screen.getByTestId("chat-msg-assistant")
      expect(assistant).toHaveTextContent("hello")
      expect(assistant).toHaveTextContent("world")
    })
    expect(screen.getByTestId("chat-msg-user")).toHaveTextContent("what's new?")

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe("/api/chat")
    expect(init.method).toBe("POST")
    const body = JSON.parse(init.body as string) as {
      date: string
      question: string
    }
    expect(body.question).toBe("what's new?")
    expect(body.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it("renders markdown in assistant output via react-markdown", async () => {
    fetchMock.mockResolvedValueOnce(sseResponse([{ data: "**bold** text" }]))
    const user = userEvent.setup()
    render(<ChatForm />)
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      const assistant = screen.getByTestId("chat-msg-assistant")
      expect(assistant.querySelector("strong")).toHaveTextContent("bold")
    })
  })

  it("retries exactly once on stale_session with the same payload", async () => {
    fetchMock
      .mockResolvedValueOnce(
        sseResponse([{ event: "stale_session", data: "expired" }]),
      )
      .mockResolvedValueOnce(sseResponse([{ data: "after retry" }]))
    const user = userEvent.setup()
    render(<ChatForm />)
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "after retry",
      )
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [first, second] = fetchMock.mock.calls as Array<[string, RequestInit]>
    expect(first[1].body).toBe(second[1].body)
  })

  it("shows event:error inline and does not retry", async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse([{ event: "error", data: "boom" }]),
    )
    const user = userEvent.setup()
    render(<ChatForm />)
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-error")).toHaveTextContent("boom")
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it("hides the mic button when SpeechRecognition is unavailable", () => {
    render(<ChatForm />)
    expect(screen.queryByTestId("mic-button")).toBeNull()
    expect(screen.getByTestId("mic-unsupported")).toBeInTheDocument()
  })

  it("shows the mic button when SpeechRecognition is available", () => {
    class FakeRecognition {
      lang = ""
      continuous = false
      interimResults = false
      onresult: ((e: unknown) => void) | null = null
      onend: (() => void) | null = null
      onerror: ((e: unknown) => void) | null = null
      start() {}
      stop() {}
    }
    ;(window as unknown as { SpeechRecognition: unknown }).SpeechRecognition =
      FakeRecognition
    render(<ChatForm />)
    expect(screen.getByTestId("mic-button")).toBeInTheDocument()
    expect(screen.queryByTestId("mic-unsupported")).toBeNull()
  })

  it("hydrates the input from sessionStorage on mount", async () => {
    window.sessionStorage.setItem(DRAFT_KEY, "draft in progress")
    render(<ChatForm />)
    const input = await screen.findByTestId("chat-input")
    await waitFor(() => {
      expect(input).toHaveValue("draft in progress")
    })
  })

  it("persists the draft on each change and clears it on successful send", async () => {
    fetchMock.mockResolvedValueOnce(sseResponse([{ data: "ok" }]))
    const user = userEvent.setup()
    render(<ChatForm />)
    const input = screen.getByTestId("chat-input")
    await user.type(input, "ab")
    await waitFor(() => {
      expect(window.sessionStorage.getItem(DRAFT_KEY)).toBe("ab")
    })
    await user.click(screen.getByTestId("send-button"))
    await waitFor(() => {
      expect(window.sessionStorage.getItem(DRAFT_KEY)).toBeNull()
    })
    expect(input).toHaveValue("")
  })

  it("shows the session-expired card on 401", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 401 }))
    const user = userEvent.setup()
    render(<ChatForm />)
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("session-expired")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("chat-input")).toBeNull()
  })
})
