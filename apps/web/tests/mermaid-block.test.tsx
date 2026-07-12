import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { MermaidBlock } from "@/components/ui/MermaidBlock"

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (id: string) => ({
      svg: `<svg data-testid="mermaid-svg" id="${id}"></svg>`,
    })),
  },
}))

describe("MermaidBlock", () => {
  it("renders the SVG produced by mermaid.render (success)", async () => {
    render(<MermaidBlock code="flowchart TB\n  A --> B" />)

    await waitFor(() => {
      expect(screen.getByTestId("mermaid-svg")).toBeInTheDocument()
    })
  })
})
