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
    if (event !== null) events.push(event)
  }
  return { events, rest }
}

/**
 * Parse one raw SSE event block (the text between "\n\n" separators), or null
 * for a block that carries nothing at all — a stray separator or a
 * comment-only block — so consumers don't see spurious
 * `{type: "message", data: ""}` events.
 *
 * A *present but empty* `data:` field is not one of those: it is how a blank
 * source line is encoded, and dropping it collapses markdown paragraph breaks
 * ("\n\n" becomes "\n"). Typed events are kept even with no `data:` field at
 * all — they carry control meaning.
 */
function parseSseEventBlock(raw: string): SseEvent | null {
  let type = "message"
  const data: string[] = []
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) type = line.slice(6).replace(/^ /, "")
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""))
  }
  if (data.length === 0 && type === "message") return null
  return { type, data: data.join("\n") }
}

/**
 * Append one `message` event's data to the text accumulated so far.
 *
 * The backend encodes the answer one source line per event, so the newline
 * between them only exists implicitly — this restores it. Shared by both chat
 * stores so the joining rule (and the blank-line handling that depends on it)
 * can't drift apart.
 */
export function appendSseMessageToAnswer(answer: string, data: string): string {
  return answer ? `${answer}\n${data}` : data
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
    // Flush a final event that arrived without a trailing "\n\n". The parser
    // applies the same filter, so a trailing typed control event with no data
    // (e.g. `event: stale_session`) isn't silently dropped.
    const tail = parseSseEventBlock(buffer)
    if (tail !== null) yield tail
  } finally {
    signal?.removeEventListener("abort", onAbort)
  }
}
