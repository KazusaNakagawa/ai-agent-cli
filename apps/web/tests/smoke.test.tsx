import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { OnboardedHome } from "@/components/OnboardedHome"

describe("OnboardedHome", () => {
  it("renders the shadcn Card title and post-onboarding hint", () => {
    render(<OnboardedHome />)
    expect(screen.getByText("ai-agent")).toBeInTheDocument()
    expect(screen.getByText(/Setup complete/i)).toBeInTheDocument()
    expect(screen.getByText(/Main sidebar UI is coming in #71/)).toBeInTheDocument()
  })
})
