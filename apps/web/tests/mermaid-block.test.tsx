import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { MermaidBlock } from "@/components/ui/MermaidBlock"

const renderMock = vi.fn()

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: (...args: unknown[]) => renderMock(...args),
  },
}))

describe("MermaidBlock", () => {
  it("renders the SVG produced by mermaid.render (success)", async () => {
    renderMock.mockResolvedValueOnce({ svg: '<svg data-testid="mermaid-svg"></svg>' })
    render(<MermaidBlock code="flowchart TB\n  A --> B" />)

    await waitFor(() => {
      expect(screen.getByTestId("mermaid-svg")).toBeInTheDocument()
    })
  })

  it("shows an error message and a collapsible source block on invalid mermaid syntax (failure)", async () => {
    renderMock.mockRejectedValueOnce(new Error("Parse error on line 1"))
    render(<MermaidBlock code="not a valid diagram" />)

    await waitFor(() => {
      expect(screen.getByText(/Mermaid render error: Parse error on line 1/)).toBeInTheDocument()
    })
    expect(screen.getByText("Show source")).toBeInTheDocument()
    expect(screen.getByText("not a valid diagram")).toBeInTheDocument()
  })
})
