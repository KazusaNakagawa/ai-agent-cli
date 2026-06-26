import { createRef } from "react"
import { describe, expect, it, vi } from "vitest"
import { insertAtCursor } from "@/lib/insertAtCursor"

describe("insertAtCursor", () => {
  it("inserts snippet at cursor position", () => {
    const el = document.createElement("textarea")
    el.value = "hello world"
    el.selectionStart = 5
    el.selectionEnd = 5
    const ref = { current: el } as React.RefObject<HTMLTextAreaElement>
    const setValue = vi.fn()

    insertAtCursor(ref, setValue, "![image](url)")

    expect(setValue).toHaveBeenCalledWith("hello![image](url) world")
  })

  it("replaces selected text with snippet", () => {
    const el = document.createElement("textarea")
    el.value = "hello world"
    el.selectionStart = 6
    el.selectionEnd = 11
    const ref = { current: el } as React.RefObject<HTMLTextAreaElement>
    const setValue = vi.fn()

    insertAtCursor(ref, setValue, "![image](url)")

    expect(setValue).toHaveBeenCalledWith("hello ![image](url)")
  })

  it("does nothing if ref.current is null", () => {
    const ref = { current: null } as React.RefObject<HTMLTextAreaElement>
    const setValue = vi.fn()
    expect(() => insertAtCursor(ref, setValue, "x")).not.toThrow()
    expect(setValue).not.toHaveBeenCalled()
  })
})
