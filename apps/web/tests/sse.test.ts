import { describe, expect, it } from "vitest"

import { parseSseChunk, readSseEvents, type SseEvent } from "@/lib/sse"

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c))
      controller.close()
    },
  })
}

async function collect(gen: AsyncGenerator<SseEvent>): Promise<SseEvent[]> {
  const out: SseEvent[] = []
  for await (const ev of gen) out.push(ev)
  return out
}

describe("parseSseChunk", () => {
  it("parses typed and default events, keeping the unconsumed tail", () => {
    const { events, rest } = parseSseChunk(
      "data: hello\n\nevent: error\ndata: boom\n\ndata: partial",
    )
    expect(events).toEqual([
      { type: "message", data: "hello" },
      { type: "error", data: "boom" },
    ])
    expect(rest).toBe("data: partial")
  })

  it("joins multi-line data and tolerates a missing space after the colon", () => {
    const { events } = parseSseChunk("data:line1\ndata: line2\n\n")
    expect(events).toEqual([{ type: "message", data: "line1\nline2" }])
  })
})

describe("readSseEvents", () => {
  it("yields events across chunk boundaries and flushes the tail", async () => {
    const events = await collect(
      readSseEvents(streamOf(["data: a\n\nda", "ta: b"])),
    )
    expect(events).toEqual([
      { type: "message", data: "a" },
      { type: "message", data: "b" },
    ])
  })

  it("ends cleanly when the signal aborts mid-stream", async () => {
    const controller = new AbortController()
    // A stream that emits one event then stays open.
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(encoder.encode("data: first\n\n"))
      },
    })
    const seen: SseEvent[] = []
    for await (const ev of readSseEvents(stream, controller.signal)) {
      seen.push(ev)
      controller.abort()
    }
    expect(seen).toEqual([{ type: "message", data: "first" }])
    expect(controller.signal.aborted).toBe(true)
  })
})
