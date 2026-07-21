/** Shared Server-Sent Events parsing (used by chatJobStore and JournalScreen). */

export type SseEvent = { type: string; data: string }

/**
 * Streaming SSE parser: events end at "\n\n"; multi-line `data:` fields join
 * with "\n". Returns completed events plus the unconsumed tail of the buffer.
 * Events without an `event:` line get the SSE default type "message".
 */
export function parseSseChunk(buffer: string): { events: SseEvent[]; rest: string } {
  const events: SseEvent[] = []
  let rest = buffer
  let idx: number
  while ((idx = rest.indexOf("\n\n")) !== -1) {
    const event = parseSseEventBlock(rest.slice(0, idx))
    rest = rest.slice(idx + 2)
    // Skip fully-empty blocks (stray separators / comment-only blocks) so
    // consumers don't see spurious `{type: "message", data: ""}` events.
    // Typed events are kept even with empty data — they carry control meaning.
    if (event.data || event.type !== "message") events.push(event)
  }
  return { events, rest }
}

/** Parse one raw SSE event block (the text between "\n\n" separators). */
function parseSseEventBlock(raw: string): SseEvent {
  let type = "message"
  const data: string[] = []
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) type = line.slice(6).replace(/^ /, "")
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""))
  }
  return { type, data: data.join("\n") }
}

/**
 * Read an SSE body as an async generator of events.
 *
 * When `signal` aborts, the reader is cancelled so the pending read resolves
 * and the generator ends cleanly — callers check `signal.aborted` afterwards.
 * An AbortError surfacing from the read while aborted is swallowed (it is the
 * expected way a cancelled fetch body terminates); other errors propagate.
 */
export async function* readSseEvents(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  const reader = body.getReader()
  const onAbort = () => void reader.cancel().catch(() => {})
  signal?.addEventListener("abort", onAbort, { once: true })
  const decoder = new TextDecoder()
  let buffer = ""
  try {
    while (true) {
      let chunk: ReadableStreamReadResult<Uint8Array>
      try {
        chunk = await reader.read()
      } catch (e) {
        if (signal?.aborted && e instanceof DOMException && e.name === "AbortError") return
        throw e
      }
      if (chunk.done) break
      buffer += decoder.decode(chunk.value, { stream: true })
      const { events, rest } = parseSseChunk(buffer)
      buffer = rest
      for (const ev of events) yield ev
    }
    // Flush a final event that arrived without a trailing "\n\n". Keep the
    // same filter as parseSseChunk so a trailing typed control event with no
    // data (e.g. `event: stale_session`) isn't silently dropped.
    const tail = parseSseEventBlock(buffer)
    if (tail.data || tail.type !== "message") yield tail
  } finally {
    signal?.removeEventListener("abort", onAbort)
  }
}
