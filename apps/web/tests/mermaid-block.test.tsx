import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { MermaidBlock } from "@/components/ui/MermaidBlock"

const renderMock = vi.fn()
const initializeMock = vi.fn()

vi.mock("mermaid", () => ({
  default: {
    initialize: (...args: unknown[]) => initializeMock(...args),
    render: (...args: unknown[]) => renderMock(...args),
  },
}))

vi.mock("@/components/ui/MermaidModal", () => ({
  MermaidModal: ({ onClose }: { svg: string; onClose: () => void }) => (
    <div data-testid="mermaid-modal">
      <button type="button" onClick={onClose}>
        close
      </button>
    </div>
  ),
}))

describe("MermaidBlock", () => {
  it("renders the SVG produced by mermaid.render (success)", async () => {
    renderMock.mockResolvedValueOnce({ svg: '<svg data-testid="mermaid-svg"></svg>' })
    render(<MermaidBlock code="flowchart TB\n  A --> B" />)

    await waitFor(() => {
      expect(screen.getByTestId("mermaid-svg")).toBeInTheDocument()
    })
    // This is the first mount in the suite, so mermaid.initialize runs here
    // with the module's fixed config (module-level flag skips later mounts).
    expect(initializeMock).toHaveBeenCalledWith({
      startOnLoad: false,
      securityLevel: "strict",
    })
  })

  it("does not call mermaid.initialize again on a second mount (efficiency)", async () => {
    initializeMock.mockClear()
    renderMock.mockResolvedValueOnce({ svg: '<svg data-testid="mermaid-svg-2"></svg>' })
    render(<MermaidBlock code="flowchart TB\n  C --> D" />)

    await waitFor(() => {
      expect(screen.getByTestId("mermaid-svg-2")).toBeInTheDocument()
    })
    expect(initializeMock).not.toHaveBeenCalled()
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

  it("opens MermaidModal when the rendered SVG is clicked, and closes it via onClose (success)", async () => {
    renderMock.mockResolvedValueOnce({ svg: '<svg data-testid="mermaid-svg-click"></svg>' })
    render(<MermaidBlock code="flowchart TB\n  A --> B" />)

    const svgContainer = await screen.findByTestId("mermaid-svg-click")
    expect(screen.queryByTestId("mermaid-modal")).not.toBeInTheDocument()

    fireEvent.click(svgContainer)
    expect(screen.getByTestId("mermaid-modal")).toBeInTheDocument()

    fireEvent.click(screen.getByText("close"))
    expect(screen.queryByTestId("mermaid-modal")).not.toBeInTheDocument()
  })
})
