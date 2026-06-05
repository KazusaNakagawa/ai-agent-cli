import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { StrictMode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ChatForm } from "@/components/screens/ChatForm"
import { ChatJobStateProvider } from "@/lib/chatJobStore"
import { ChatStateProvider } from "@/lib/chatStore"

function renderChatForm() {
  return render(
    <ChatStateProvider>
      <ChatJobStateProvider>
        <ChatForm />
      </ChatJobStateProvider>
    </ChatStateProvider>,
  )
}

function renderChatFormStrict() {
  return render(
    <StrictMode>
      <ChatStateProvider>
        <ChatJobStateProvider>
          <ChatForm />
        </ChatJobStateProvider>
      </ChatStateProvider>
    </StrictMode>,
  )
}

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

  // Per-URL response queue. URL-keyed (rather than vitest's global
  // once-queue) keeps the mount-time /api/credentials fetch from
  // accidentally consuming a chat-POST response.
  type Handler = (init?: RequestInit) => Promise<Response> | Response
  let queues: Record<string, Handler[]>
  let nextJobId: number

  function on(url: string, handler: Handler) {
    if (!queues[url]) queues[url] = []
    queues[url].push(handler)
  }

  // The backend now answers /api/chat with `202 {job_id}`, then streams via
  // GET /api/chat/{job_id}/stream. Most tests just want to set "given this
  // chat turn, the SSE looks like X" — this helper queues the canned 202 and
  // the SSE response together, with a unique job_id per call so concurrent
  // turns (e.g. the stale_session retry) don't collide on the same URL key.
  function chatRoundtrip(streamHandler: Handler): string {
    const jobId = `job-${nextJobId++}`
    on("/api/chat", () =>
      new Response(JSON.stringify({ job_id: jobId, status: "pending" }), {
        status: 202,
        headers: { "content-type": "application/json" },
      }),
    )
    on(`/api/chat/${jobId}/stream`, streamHandler)
    return jobId
  }

  function mockCreds(creds: Record<string, boolean> = {}) {
    return new Response(JSON.stringify(creds), {
      status: 200,
      headers: { "content-type": "application/json" },
    })
  }

  beforeEach(() => {
    queues = {}
    nextJobId = 1
    fetchMock.mockReset()
    fetchMock.mockImplementation(async (url: string | URL, init?: RequestInit) => {
      const u = typeof url === "string" ? url : url.toString()
      const queue = queues[u]
      if (queue && queue.length > 0) {
        const next = queue.shift()!
        return await next(init)
      }
      // Default credentials response so existing tests don't have to queue
      // one explicitly. Tests can override by calling on("/api/credentials", ...).
      if (u === "/api/credentials") return mockCreds()
      throw new Error(`Unmocked fetch in ChatForm test: ${u}`)
    })
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
    renderChatForm()
    expect(screen.getByTestId("chat-input")).toBeInTheDocument()
    expect(screen.getByTestId("send-button")).toBeDisabled()
  })

  it("enables send once the input is non-empty", async () => {
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "hi")
    expect(screen.getByTestId("send-button")).not.toBeDisabled()
  })

  it("POSTs today's date + question and streams assistant output", async () => {
    chatRoundtrip(() => sseResponse([{ data: "hello" }, { data: "world" }]))
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "what's new?")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      const assistant = screen.getByTestId("chat-msg-assistant")
      expect(assistant).toHaveTextContent("hello")
      expect(assistant).toHaveTextContent("world")
    })
    expect(screen.getByTestId("chat-msg-user")).toHaveTextContent("what's new?")

    const chatCall = fetchMock.mock.calls.find(
      ([u]) => u === "/api/chat",
    ) as [string, RequestInit] | undefined
    expect(chatCall).toBeDefined()
    expect(chatCall![1].method).toBe("POST")
    const body = JSON.parse(chatCall![1].body as string) as {
      date: string
      question: string
    }
    expect(body.question).toBe("what's new?")
    expect(body.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it("renders markdown in assistant output via react-markdown", async () => {
    chatRoundtrip(() => sseResponse([{ data: "**bold** text" }]))
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      const assistant = screen.getByTestId("chat-msg-assistant")
      expect(assistant.querySelector("strong")).toHaveTextContent("bold")
    })
  })

  it("strips dangerous raw HTML from assistant markdown (rehype-sanitize)", async () => {
    chatRoundtrip(() =>
      sseResponse([{ data: "<img src=x onerror=alert(1)> after" }]),
    )
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent("after")
    })
    const assistant = screen.getByTestId("chat-msg-assistant")
    expect(assistant.querySelector("img")).toBeNull()
    expect(assistant.innerHTML).not.toMatch(/onerror/i)
  })

  it("retries exactly once on stale_session with the same payload", async () => {
    chatRoundtrip(() =>
      sseResponse([{ event: "stale_session", data: "expired" }]),
    )
    chatRoundtrip(() => sseResponse([{ data: "after retry" }]))
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "after retry",
      )
    })
    const chatCalls = fetchMock.mock.calls.filter(
      ([u]) => u === "/api/chat",
    ) as Array<[string, RequestInit]>
    expect(chatCalls).toHaveLength(2)
    expect(chatCalls[0][1].body).toBe(chatCalls[1][1].body)
  })

  it("shows event:error inline and does not retry", async () => {
    chatRoundtrip(() => sseResponse([{ event: "error", data: "boom" }]))
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-error")).toHaveTextContent("boom")
    })
    const chatCalls = fetchMock.mock.calls.filter(([u]) => u === "/api/chat")
    expect(chatCalls).toHaveLength(1)
  })

  it("does not send on Enter while IME composition is active", async () => {
    const user = userEvent.setup()
    renderChatForm()
    const input = screen.getByTestId("chat-input")
    await user.type(input, "あ")
    fireEvent.compositionStart(input)
    fireEvent.keyDown(input, { key: "Enter", isComposing: true })
    await new Promise((r) => setTimeout(r, 0))
    const chatCalls = fetchMock.mock.calls.filter(([u]) => u === "/api/chat")
    expect(chatCalls).toHaveLength(0)
  })

  it("sends on Enter after compositionend fires", async () => {
    chatRoundtrip(() => sseResponse([{ data: "ok" }]))
    const user = userEvent.setup()
    renderChatForm()
    const input = screen.getByTestId("chat-input")
    await user.type(input, "あ")
    fireEvent.compositionStart(input)
    fireEvent.compositionEnd(input)
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent("ok")
    })
    const chatCalls = fetchMock.mock.calls.filter(([u]) => u === "/api/chat")
    expect(chatCalls).toHaveLength(1)
  })

  it("hides the mic button when SpeechRecognition is unavailable", () => {
    renderChatForm()
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
    renderChatForm()
    expect(screen.getByTestId("mic-button")).toBeInTheDocument()
    expect(screen.queryByTestId("mic-unsupported")).toBeNull()
  })

  it("preserves the already-typed text when the mic starts", async () => {
    type FakeRec = {
      lang: string
      continuous: boolean
      interimResults: boolean
      onresult: ((e: { results: { 0: { transcript: string } }[] }) => void) | null
      onend: (() => void) | null
      onerror: ((e: unknown) => void) | null
      start: () => void
      stop: () => void
    }
    let lastRec: FakeRec | null = null
    class FakeRecognition implements FakeRec {
      lang = ""
      continuous = false
      interimResults = false
      onresult: FakeRec["onresult"] = null
      onend: FakeRec["onend"] = null
      onerror: FakeRec["onerror"] = null
      start() {
        lastRec = this
      }
      stop() {}
    }
    ;(window as unknown as { SpeechRecognition: unknown }).SpeechRecognition =
      FakeRecognition

    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "前段の文字列")
    await user.click(screen.getByTestId("mic-button"))

    expect(lastRec).not.toBeNull()
    act(() => {
      lastRec!.onresult!({
        results: [{ 0: { transcript: "音声入力" } }] as unknown as {
          0: { transcript: string }
        }[],
      } as { results: { 0: { transcript: string } }[] })
    })

    expect(screen.getByTestId("chat-input")).toHaveValue("前段の文字列 音声入力")
  })

  it("returns the mic button to idle after stop, even under StrictMode double-mount", async () => {
    type FakeRec = {
      lang: string
      continuous: boolean
      interimResults: boolean
      onresult: ((e: { results: { 0: { transcript: string } }[] }) => void) | null
      onend: (() => void) | null
      onerror: ((e: unknown) => void) | null
      start: () => void
      stop: () => void
    }
    class FakeRecognition implements FakeRec {
      lang = ""
      continuous = false
      interimResults = false
      onresult: FakeRec["onresult"] = null
      onend: FakeRec["onend"] = null
      onerror: FakeRec["onerror"] = null
      start() {}
      stop() {
        // Simulate the browser firing onend in response to stop().
        this.onend?.()
      }
    }
    ;(window as unknown as { SpeechRecognition: unknown }).SpeechRecognition =
      FakeRecognition

    const user = userEvent.setup()
    renderChatFormStrict()

    const micBtn = await screen.findByTestId("mic-button")
    expect(micBtn).toHaveAttribute("aria-pressed", "false")

    await user.click(micBtn)
    expect(screen.getByTestId("mic-button")).toHaveAttribute(
      "aria-pressed",
      "true",
    )

    // Click again to stop. Before the fix, StrictMode's mount → cleanup →
    // remount sequence left mountedRef stuck at false, so the onend stop
    // callback would skip setListening(false) and the button would stay
    // pressed.
    await user.click(screen.getByTestId("mic-button"))
    await waitFor(() => {
      expect(screen.getByTestId("mic-button")).toHaveAttribute(
        "aria-pressed",
        "false",
      )
    })
  })

  it("hydrates the input from sessionStorage on mount", async () => {
    window.sessionStorage.setItem(DRAFT_KEY, "draft in progress")
    renderChatForm()
    const input = await screen.findByTestId("chat-input")
    await waitFor(() => {
      expect(input).toHaveValue("draft in progress")
    })
  })

  it("persists the draft on each change and clears it on successful send", async () => {
    chatRoundtrip(() => sseResponse([{ data: "ok" }]))
    const user = userEvent.setup()
    renderChatForm()
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
    on("/api/chat", () => new Response("", { status: 401 }))
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("session-expired")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("chat-input")).toBeNull()
  })

  // ----- Notion save (Issue #87) ----------------------------------------

  async function sendOneTurn(user: ReturnType<typeof userEvent.setup>) {
    chatRoundtrip(() => sseResponse([{ data: "an answer" }]))
    await user.type(screen.getByTestId("chat-input"), "a question")
    await user.click(screen.getByTestId("send-button"))
    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "an answer",
      )
    })
  }

  it("disables the Notion button when credentials are absent", async () => {
    const user = userEvent.setup()
    renderChatForm()
    await sendOneTurn(user)
    const button = await screen.findByTestId("notion-save-button")
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute(
      "title",
      expect.stringContaining("Notion 認証情報が未設定"),
    )
  })

  it("disables the Notion button when only NOTION_API_KEY is set", async () => {
    on("/api/credentials", () =>
      mockCreds({ NOTION_API_KEY: true, NOTION_DATABASE_ID: false }),
    )
    const user = userEvent.setup()
    renderChatForm()
    await sendOneTurn(user)
    const button = await screen.findByTestId("notion-save-button")
    expect(button).toBeDisabled()
  })

  it("enables the Notion button when both NOTION_* keys are set", async () => {
    on("/api/credentials", () =>
      mockCreds({ NOTION_API_KEY: true, NOTION_DATABASE_ID: true }),
    )
    const user = userEvent.setup()
    renderChatForm()
    await sendOneTurn(user)
    await waitFor(() => {
      expect(screen.getByTestId("notion-save-button")).not.toBeDisabled()
    })
  })

  it("POSTs the Q&A on click and surfaces the returned URL", async () => {
    on("/api/credentials", () =>
      mockCreds({ NOTION_API_KEY: true, NOTION_DATABASE_ID: true }),
    )
    let importBody: string | null = null
    on("/api/chat/notion-import", (init) => {
      importBody = (init?.body as string) ?? null
      return new Response(
        JSON.stringify({ url: "https://www.notion.so/abc", summary: "ok" }),
        { status: 200, headers: { "content-type": "application/json" } },
      )
    })
    const user = userEvent.setup()
    renderChatForm()
    await sendOneTurn(user)
    await waitFor(() => {
      expect(screen.getByTestId("notion-save-button")).not.toBeDisabled()
    })
    // The model selector was removed (PR #110 review feedback): saving the
    // already-streamed answer doesn't benefit from a fresh model choice —
    // the only work left is a Notion API append, for which the backend
    // default (sonnet) is sufficient. So no UI control to assert here.
    expect(screen.queryByTestId("notion-model-select")).toBeNull()
    await user.click(screen.getByTestId("notion-save-button"))

    await waitFor(() => {
      expect(screen.getByTestId("notion-save-link")).toHaveAttribute(
        "href",
        "https://www.notion.so/abc",
      )
    })
    expect(screen.getByTestId("notion-save-button")).toBeDisabled()
    expect(importBody).not.toBeNull()
    const sent = JSON.parse(importBody!) as {
      date: string
      question: string
      answer: string
      model?: string
    }
    expect(sent.question).toBe("a question")
    expect(sent.answer).toBe("an answer")
    expect(sent.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    // model is omitted from the request body now that the UI no longer
    // surfaces a picker; the backend's Pydantic default (sonnet) kicks in.
    expect(sent.model).toBeUndefined()
  })

  it("keeps Notion save disabled while the assistant message is still streaming", async () => {
    on("/api/credentials", () =>
      mockCreds({ NOTION_API_KEY: true, NOTION_DATABASE_ID: true }),
    )

    // Hand-rolled SSE stream we can hold open: enqueue a partial chunk, let
    // the UI render, then assert the button is disabled before closing.
    const encoder = new TextEncoder()
    let controllerRef: ReadableStreamDefaultController<Uint8Array> | null = null
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controllerRef = controller
        controller.enqueue(encoder.encode("data: partial\n\n"))
      },
    })
    chatRoundtrip(() => new Response(stream, { status: 200 }))

    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    // First chunk arrived — content rendered, button visible but disabled.
    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "partial",
      )
    })
    const button = screen.getByTestId("notion-save-button")
    expect(button).toBeDisabled()

    // Close the stream → busy flips false → button re-enables.
    controllerRef!.close()
    await waitFor(() => {
      expect(screen.getByTestId("notion-save-button")).not.toBeDisabled()
    })
  })

  it("surfaces the backend detail verbatim on 4xx (skill failure)", async () => {
    on("/api/credentials", () =>
      mockCreds({ NOTION_API_KEY: true, NOTION_DATABASE_ID: true }),
    )
    on("/api/chat/notion-import", () =>
      new Response(
        JSON.stringify({
          detail:
            "No Notion briefing page found for 2026-05-30 (skill report: 対象ページが見つかりませんでした)",
        }),
        { status: 404, headers: { "content-type": "application/json" } },
      ),
    )
    const user = userEvent.setup()
    renderChatForm()
    await sendOneTurn(user)
    await waitFor(() => {
      expect(screen.getByTestId("notion-save-button")).not.toBeDisabled()
    })
    await user.click(screen.getByTestId("notion-save-button"))

    await waitFor(() => {
      expect(screen.getByTestId("notion-save-error")).toHaveTextContent(
        "No Notion briefing page found for 2026-05-30",
      )
    })
    // After an error the button re-enables so the user can retry.
    expect(screen.getByTestId("notion-save-button")).not.toBeDisabled()
  })

  // ----- Cancel in-flight streaming (Issue #98) ------------------------

  // Open a streaming response that emits one chunk and stays open until the
  // request's AbortSignal fires — emulating real fetch+SSE cancellation so
  // send()'s reader.read() actually resolves after cancel.
  function openChatStream(firstChunk = "partial"): Handler {
    const encoder = new TextEncoder()
    return (init) => {
      const signal = init?.signal ?? undefined
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode(`data: ${firstChunk}\n\n`))
          signal?.addEventListener("abort", () => {
            try {
              controller.close()
            } catch {
              // already closed
            }
          })
        },
      })
      return new Response(stream, { status: 200 })
    }
  }

  it("replaces Send with Cancel while streaming", async () => {
    chatRoundtrip(openChatStream())
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "my question")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "partial",
      )
    })
    expect(screen.queryByTestId("send-button")).toBeNull()
    expect(screen.getByTestId("cancel-button")).toBeInTheDocument()

    // Clean up so the test doesn't leave a pending stream.
    await user.click(screen.getByTestId("cancel-button"))
    await waitFor(() => {
      expect(screen.getByTestId("send-button")).toBeInTheDocument()
    })
  })

  it("clicking Cancel aborts, marks the message cancelled, and restores the question", async () => {
    chatRoundtrip(openChatStream())
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "my question")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "partial",
      )
    })
    await user.click(screen.getByTestId("cancel-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-cancelled")).toHaveTextContent("Cancelled")
    })
    expect(screen.getByTestId("chat-input")).toHaveValue("my question")
    expect(screen.queryByTestId("chat-error")).toBeNull()
    // Cancel button gone, Send back so the user can resend.
    await waitFor(() => {
      expect(screen.getByTestId("send-button")).toBeInTheDocument()
    })
  })

  it("Esc cancels the in-flight stream", async () => {
    chatRoundtrip(openChatStream("hi"))
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent("hi")
    })
    await user.keyboard("{Escape}")

    await waitFor(() => {
      expect(screen.getByTestId("chat-cancelled")).toBeInTheDocument()
    })
    expect(screen.getByTestId("chat-input")).toHaveValue("q")
  })

  it("keeps the textarea editable while streaming", async () => {
    chatRoundtrip(openChatStream())
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "partial",
      )
    })
    expect(screen.getByTestId("chat-input")).not.toBeDisabled()

    await user.click(screen.getByTestId("cancel-button"))
    await waitFor(() => {
      expect(screen.getByTestId("send-button")).toBeInTheDocument()
    })
  })

  it("does not log a React warning when unmounted mid-stream", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {})
    chatRoundtrip(openChatStream())
    const user = userEvent.setup()
    const { unmount } = renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))
    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "partial",
      )
    })
    // useAbortableMount's cleanup aborts the in-flight fetch on unmount —
    // any post-unmount setState would surface as a React console.error.
    unmount()
    await new Promise((r) => setTimeout(r, 20))
    expect(errorSpy).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it("allows sending a fresh request after cancel", async () => {
    chatRoundtrip(openChatStream("first"))
    chatRoundtrip(() => sseResponse([{ data: "second answer" }]))

    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q1")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent("first")
    })
    await user.click(screen.getByTestId("cancel-button"))

    await waitFor(() => {
      expect(screen.getByTestId("send-button")).toBeInTheDocument()
    })
    const input = screen.getByTestId("chat-input")
    await user.clear(input)
    await user.type(input, "q2")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      const assistants = screen.getAllByTestId("chat-msg-assistant")
      expect(assistants[assistants.length - 1]).toHaveTextContent(
        "second answer",
      )
    })
  })

  // ----- Resume in-flight job on mount (Issue #125) --------------------

  it("hydrates an in-flight job from sessionStorage and resumes the stream", async () => {
    const CHAT_JOB_KEY = "ai-agent:chat-job:v1"
    window.sessionStorage.setItem(
      CHAT_JOB_KEY,
      JSON.stringify({
        jobId: "resume-2",
        status: "running",
        question: "今日の株価は？",
        date: "2026-06-06",
        assistantContent: "",
        error: null,
        sessionExpired: false,
        staleSession: false,
      }),
    )
    on("/api/chat/resume-2/stream", () =>
      sseResponse([{ data: "Resumed answer." }]),
    )

    renderChatForm()

    // The persisted user question shows up immediately as the in-flight
    // turn, alongside whatever committed history was already there.
    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-user")).toHaveTextContent(
        "今日の株価は？",
      )
    })
    // The watch loop resumes the GET stream against the persisted job_id
    // and fills the assistant message from the replay.
    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "Resumed answer.",
      )
    })
    // The originating tab is the one that committed the turn — this
    // (hydrated) tab must NOT also append it to chatStore, otherwise we'd
    // double-list the turn on next mount. The sessionStorage entry should
    // also be cleared once the job terminates.
    await waitFor(() => {
      expect(window.sessionStorage.getItem(CHAT_JOB_KEY)).toBeNull()
    })
    // Only one user message (the in-flight one) — the hydrated tab didn't
    // commit a second copy.
    expect(screen.getAllByTestId("chat-msg-user")).toHaveLength(1)
  })

  // ----- Up/Down history recall (Issue #117) ---------------------------

  const CHAT_HISTORY_KEY = "ai-agent:chat-history:v1"

  // Seed the chat store directly via sessionStorage so each test can start
  // with a controlled history without going through real POST→stream
  // roundtrips for every entry.
  function seedHistory(questions: string[]): void {
    const messages = questions.flatMap((q) => [
      { role: "user" as const, content: q },
      { role: "assistant" as const, content: "answer for " + q },
    ])
    window.sessionStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(messages))
  }

  function getInput(): HTMLTextAreaElement {
    return screen.getByTestId("chat-input") as HTMLTextAreaElement
  }

  it("Up in an empty textarea recalls the most recent user question", async () => {
    seedHistory(["first", "second", "third"])
    renderChatForm()
    const input = await screen.findByTestId("chat-input")
    await waitFor(() => expect(input).toBeInTheDocument())

    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("third"))
  })

  it("subsequent Up keystrokes walk further back through history", async () => {
    seedHistory(["first", "second", "third"])
    renderChatForm()
    const input = getInput()

    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("third"))
    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("second"))
    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("first"))
    // Up at the oldest is a no-op (preventDefault keeps caret stable but
    // value doesn't regress further).
    fireEvent.keyDown(input, { key: "ArrowUp" })
    await new Promise((r) => setTimeout(r, 10))
    expect(input).toHaveValue("first")
  })

  it("Down walks forward and Down past newest restores the saved draft", async () => {
    seedHistory(["first", "second"])
    const user = userEvent.setup()
    renderChatForm()
    const input = getInput()
    // User had a draft in progress before nav.
    await user.type(input, "draft")

    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("second"))
    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("first"))
    fireEvent.keyDown(input, { key: "ArrowDown" })
    await waitFor(() => expect(input).toHaveValue("second"))
    // Past the newest → original draft restored, nav state reset.
    fireEvent.keyDown(input, { key: "ArrowDown" })
    await waitFor(() => expect(input).toHaveValue("draft"))
    // A subsequent Down without a prior Up is a no-op.
    fireEvent.keyDown(input, { key: "ArrowDown" })
    await new Promise((r) => setTimeout(r, 10))
    expect(input).toHaveValue("draft")
  })

  it("Esc while navigating restores the draft without aborting any stream", async () => {
    seedHistory(["older", "newer"])
    const user = userEvent.setup()
    renderChatForm()
    const input = getInput()
    await user.type(input, "in progress")

    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("newer"))
    fireEvent.keyDown(input, { key: "Escape" })
    await waitFor(() => expect(input).toHaveValue("in progress"))
    // After Esc resets nav, a fresh Up should re-snapshot (current "in
    // progress") and walk to newest again.
    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("newer"))
    fireEvent.keyDown(input, { key: "ArrowDown" })
    await waitFor(() => expect(input).toHaveValue("in progress"))
  })

  it("Up while IME composing does not navigate history", async () => {
    seedHistory(["older"])
    renderChatForm()
    const input = getInput()

    fireEvent.compositionStart(input)
    fireEvent.keyDown(input, { key: "ArrowUp", isComposing: true })
    await new Promise((r) => setTimeout(r, 10))
    expect(input).toHaveValue("")
    fireEvent.compositionEnd(input)
    // After composition ends, Up works again.
    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("older"))
  })

  it("Up with caret not on the first line of a multi-line draft does NOT recall", async () => {
    seedHistory(["older"])
    const user = userEvent.setup()
    renderChatForm()
    const input = getInput()
    // Multi-line draft via Shift+Enter (avoids triggering send).
    await user.type(input, "line1{Shift>}{Enter}{/Shift}line2")
    expect(input.value).toBe("line1\nline2")

    // Caret in the middle of line2 — Up should naturally move it to line1,
    // not hijack to history recall.
    input.selectionStart = 8
    input.selectionEnd = 8
    fireEvent.keyDown(input, { key: "ArrowUp" })
    await new Promise((r) => setTimeout(r, 10))
    expect(input).toHaveValue("line1\nline2")

    // Caret on the first line → Up DOES recall, replacing the draft.
    input.selectionStart = 2
    input.selectionEnd = 2
    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("older"))
  })

  it("Down with caret not on the last line of a multi-line draft does NOT exit recall", async () => {
    seedHistory(["older"])
    const user = userEvent.setup()
    renderChatForm()
    const input = getInput()

    // Enter nav, then build a multi-line draft mid-nav (simulates edits).
    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("older"))
    await user.type(input, "{Shift>}{Enter}{/Shift}second")
    expect(input.value).toBe("older\nsecond")

    // Caret on the first line — Down should move it to line 2, not bail nav.
    input.selectionStart = 2
    input.selectionEnd = 2
    fireEvent.keyDown(input, { key: "ArrowDown" })
    await new Promise((r) => setTimeout(r, 10))
    expect(input).toHaveValue("older\nsecond")
  })

  it("nav state resets after a successful send", async () => {
    seedHistory(["seed"])
    chatRoundtrip(() => sseResponse([{ data: "ok" }]))
    const user = userEvent.setup()
    renderChatForm()
    const input = getInput()

    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("seed"))
    // Send the recalled question.
    await user.click(screen.getByTestId("send-button"))
    await waitFor(() => {
      const all = screen.getAllByTestId("chat-msg-assistant")
      expect(all[all.length - 1]).toHaveTextContent("ok")
    })
    // After send, input clears AND nav resets — the next Up should start
    // from the newest entry again (which is now the just-sent question).
    fireEvent.keyDown(input, { key: "ArrowUp" })
    await waitFor(() => expect(input).toHaveValue("seed"))
  })
})
