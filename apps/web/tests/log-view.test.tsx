import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { LogView } from "@/components/ui/LogView"

describe("LogView", () => {
  it("renders each line with its level keyword intact", () => {
    render(
      <LogView
        content={[
          "2026-07-12T10:00:00Z INFO server started",
          "2026-07-12T10:00:01Z ERROR connection refused",
          "plain line with no timestamp or level",
        ].join("\n")}
      />,
    )
    const el = screen.getByTestId("log-view")
    expect(el).toHaveTextContent("INFO server started")
    expect(el).toHaveTextContent("ERROR connection refused")
    expect(el).toHaveTextContent("plain line with no timestamp or level")
  })
})
