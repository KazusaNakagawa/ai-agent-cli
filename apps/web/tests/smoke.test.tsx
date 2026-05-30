import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import Home from "@/app/page"

describe("Home", () => {
  it("renders the shadcn Card title and Button", () => {
    render(<Home />)
    expect(screen.getByText("ai-agent")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /get started/i }),
    ).toBeInTheDocument()
  })
})
