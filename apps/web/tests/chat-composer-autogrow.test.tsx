import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ChatComposer } from "@/components/chat/ChatComposer"

// jsdom never runs real layout, so scrollHeight always reads 0 for every
// element. Auto-grow logic reads el.scrollHeight to size the textarea, so
// each test overrides that getter on the rendered node to simulate content
// of a given rendered height before triggering the resize effect.
function mockScrollHeight(el: HTMLElement, value: number) {
  Object.defineProperty(el, "scrollHeight", {
    configurable: true,
    value,
  })
}

function renderComposer() {
  return render(
    <ChatComposer
      input=""
      setInput={vi.fn()}
      busy={false}
      supportsMic={false}
      listening={false}
      onToggleMic={vi.fn()}
      onSend={vi.fn()}
      onCancel={vi.fn()}
    />,
  )
}

describe("ChatComposer auto-grow", () => {
  it("grows the textarea height to fit content within the max height", () => {
    renderComposer()
    const input = screen.getByTestId("chat-input")
    mockScrollHeight(input, 120)
    fireEvent.change(input, { target: { value: "line1\nline2\nline3" } })

    expect(input).toHaveStyle({ height: "120px", overflowY: "hidden" })
  })

  it("clamps growth at the max height and enables internal scroll beyond it", () => {
    renderComposer()
    const input = screen.getByTestId("chat-input")
    mockScrollHeight(input, 500)
    fireEvent.change(input, { target: { value: "a\n".repeat(50) } })

    expect(input).toHaveStyle({ height: "200px", overflowY: "auto" })
  })

  it("does not shrink below the minimum height when content is short", () => {
    renderComposer()
    const input = screen.getByTestId("chat-input")
    mockScrollHeight(input, 10)
    fireEvent.change(input, { target: { value: "hi" } })

    expect(input).toHaveStyle({ height: "40px", overflowY: "hidden" })
  })
})
