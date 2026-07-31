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

  // A blank source line is sent as a present-but-empty `data:` field. Dropping
  // it collapses markdown paragraph breaks ("\n\n" -> "\n"), so the consumer
  // must still see it — unlike a block with no `data:` field at all.
  it("keeps an empty data field so blank source lines survive", () => {
    const { events } = parseSseChunk("data: a\n\ndata: \n\ndata: b\n\n")
    expect(events).toEqual([
      { type: "message", data: "a" },
      { type: "message", data: "" },
      { type: "message", data: "b" },
    ])
  })

  it("keeps an empty data field written without the trailing space", () => {
    const { events } = parseSseChunk("data:\n\n")
    expect(events).toEqual([{ type: "message", data: "" }])
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

  it("skips empty blocks and keeps typed control events without data", async () => {
    const { events } = parseSseChunk("\n\ndata: a\n\n\n\nevent: stale_session\n\n")
    expect(events).toEqual([
      { type: "message", data: "a" },
      { type: "stale_session", data: "" },
    ])
  })

  it("emits nothing for a stream ending in a trailing separator or comments", async () => {
    const events = await collect(
      readSseEvents(streamOf(["data: a\n\n", ": keep-alive comment\n\n", "\n\n"])),
    )
    expect(events).toEqual([{ type: "message", data: "a" }])
  })

  it("flushes a trailing typed control event with no data and no separator", async () => {
    const events = await collect(
      readSseEvents(streamOf(["data: a\n\n", "event: stale_session"])),
    )
    expect(events).toEqual([
      { type: "message", data: "a" },
      { type: "stale_session", data: "" },
    ])
  })

  it("swallows AbortError from reader.read after the signal is aborted", async () => {
    const abortController = new AbortController()
    const abortError = new DOMException("The operation was aborted.", "AbortError")
    const stream = {
      getReader: () => ({
        read: () => Promise.reject(abortError),
        cancel: () => Promise.resolve(),
      }),
    } as unknown as ReadableStream<Uint8Array>

    abortController.abort()

    const events = await collect(readSseEvents(stream, abortController.signal))
    expect(events).toEqual([])
  })

  it("propagates non-AbortError rejections from reader.read", async () => {
    const error = new Error("boom")
    const stream = {
      getReader: () => ({
        read: () => Promise.reject(error),
        cancel: () => Promise.resolve(),
      }),
    } as unknown as ReadableStream<Uint8Array>

    await expect(collect(readSseEvents(stream))).rejects.toBe(error)
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
