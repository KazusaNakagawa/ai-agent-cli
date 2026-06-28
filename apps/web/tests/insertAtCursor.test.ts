import { afterEach, describe, expect, it, vi } from "vitest"
import { insertAtCursor } from "@/lib/insertAtCursor"

function makeTextarea(value: string, caret: number): HTMLTextAreaElement {
  const ta = document.createElement("textarea")
  ta.value = value
  ta.setSelectionRange(caret, caret)
  document.body.appendChild(ta)
  return ta
}

describe("insertAtCursor", () => {
  afterEach(() => {
    document.body.innerHTML = ""
    vi.restoreAllMocks()
  })

  it("splices text at the caret", () => {
    const ta = makeTextarea("ab", 1)
    expect(insertAtCursor(ta, "ab", "X")).toBe("aXb")
  })

  it("replaces the current selection", () => {
    const ta = makeTextarea("abcd", 1)
    ta.setSelectionRange(1, 3)
    expect(insertAtCursor(ta, "abcd", "X")).toBe("aXd")
  })

  it("appends when textarea is null", () => {
    expect(insertAtCursor(null, "ab", "X")).toBe("abX")
  })

  it("uses the live DOM value, not a stale captured value", () => {
    // Simulates typing during an async upload: caller captured "ab" at render
    // time, but the user has since typed so the live value is "ab hello" with
    // the caret at the end. The insert must preserve the typed characters.
    const ta = makeTextarea("ab hello", 8)
    expect(insertAtCursor(ta, "ab", "X")).toBe("ab helloX")
  })
})
