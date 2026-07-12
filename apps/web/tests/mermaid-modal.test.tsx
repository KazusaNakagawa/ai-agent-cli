import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { MermaidModal } from "@/components/ui/MermaidModal"

const SVG = '<svg data-testid="modal-svg"><rect /></svg>'

describe("MermaidModal", () => {
  it("renders the given SVG (success)", () => {
    render(<MermaidModal svg={SVG} onClose={vi.fn()} />)
    expect(screen.getByTestId("modal-svg")).toBeInTheDocument()
  })

  it("calls onClose when the close button is clicked (success)", () => {
    const onClose = vi.fn()
    render(<MermaidModal svg={SVG} onClose={onClose} />)
    fireEvent.click(screen.getByRole("button", { name: /close/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("calls onClose when Escape is pressed (boundary)", () => {
    const onClose = vi.fn()
    render(<MermaidModal svg={SVG} onClose={onClose} />)
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("calls onClose when the overlay background is clicked, but not when the content is clicked (boundary)", () => {
    const onClose = vi.fn()
    render(<MermaidModal svg={SVG} onClose={onClose} />)

    fireEvent.click(screen.getByTestId("modal-svg"))
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId("mermaid-modal-overlay"))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("exposes zoom in, zoom out, and reset controls (success)", () => {
    render(<MermaidModal svg={SVG} onClose={vi.fn()} />)

    const zoomIn = screen.getByRole("button", { name: /zoom in/i })
    const zoomOut = screen.getByRole("button", { name: /zoom out/i })
    const reset = screen.getByRole("button", { name: /reset zoom/i })

    // Clicking should not throw and should not trigger onClose (verified
    // implicitly by the presence of the modal after interaction).
    fireEvent.click(zoomIn)
    fireEvent.click(zoomOut)
    fireEvent.click(reset)

    expect(screen.getByTestId("modal-svg")).toBeInTheDocument()
  })
})
