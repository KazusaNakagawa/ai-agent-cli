import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ChatComposer } from "@/components/chat/ChatComposer"

const base = {
  input: "",
  setInput: vi.fn(),
  supportsMic: false,
  listening: false,
  onToggleMic: vi.fn(),
  onSend: vi.fn(),
  onCancel: vi.fn(),
}

describe("ChatComposer host options", () => {
  it("keeps the chat defaults", () => {
    render(
      <ChatComposer {...base} busy={false} searchHistory={false} onToggleSearchHistory={vi.fn()} />,
    )
    expect(screen.getByPlaceholderText("Ask about today's briefing…")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument()
    expect(screen.getByTestId("search-history-toggle")).toBeInTheDocument()
  })

  it("hides the history toggle when the host passes no handler", () => {
    render(<ChatComposer {...base} busy={false} />)
    expect(screen.queryByTestId("search-history-toggle")).toBeNull()
  })

  it("takes the host's placeholder and send label", () => {
    render(
      <ChatComposer {...base} busy={false} placeholder="e.g. What next?" sendLabel="Brainstorm" />,
    )
    expect(screen.getByPlaceholderText("e.g. What next?")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Brainstorm" })).toHaveAttribute(
      "data-testid",
      "send-button",
    )
  })

  it("takes the host's cancel label while busy", () => {
    render(<ChatComposer {...base} busy cancelLabel="Stop" />)
    expect(screen.getByRole("button", { name: "Stop" })).toHaveAttribute(
      "data-testid",
      "cancel-button",
    )
  })
})
