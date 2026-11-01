import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { SetupPanel } from "@/components/settings/SetupPanel"

describe("SetupPanel", () => {
  it("links to the wizard in re-run mode without touching server state", () => {
    render(<SetupPanel />)
    expect(screen.getByTestId("rerun-setup")).toHaveAttribute("href", "/?rerun=1")
  })
})
