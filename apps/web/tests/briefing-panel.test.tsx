import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { BriefingPanel } from "@/components/briefing/BriefingPanel"
import { BriefingFile } from "@/lib/briefing-types"

const FILE: BriefingFile = {
  name: "market_2026-06-21.md",
  type: "market",
  date: "2026-06-21",
  size: 1024,
}

function renderPanel(content: string | null) {
  return render(
    <BriefingPanel
      file={FILE}
      content={content}
      loading={false}
      error={null}
      fullSize={false}
      onToggleFullSize={() => {}}
      onClose={() => {}}
    />,
  )
}

describe("BriefingPanel links", () => {
  it("opens content links in a new tab with rel=noopener noreferrer", () => {
    renderPanel("[example](https://example.com)")
    const link = screen.getByRole("link", { name: "example" })
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })
})
