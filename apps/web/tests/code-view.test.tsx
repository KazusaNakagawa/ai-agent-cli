import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { CodeView } from "@/components/ui/CodeView"

describe("CodeView", () => {
  it("renders the given source text", () => {
    render(<CodeView content="def f():\n    return 1" language="python" />)
    expect(screen.getByTestId("code-view")).toHaveTextContent("def f():")
  })
})
