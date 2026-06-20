import { describe, expect, it } from "vitest"

import { extractToc, slugify } from "@/lib/briefing-toc"

describe("slugify", () => {
  it("lowercases and replaces whitespace with hyphens", () => {
    expect(slugify("Today's Market Summary")).toBe("todays-market-summary")
  })

  it("strips Japanese punctuation while keeping the characters", () => {
    expect(slugify("今日のサマリー（1文）")).toBe("今日のサマリー1文")
  })
})

describe("extractToc", () => {
  it("collects h1-h3 headings with their level and slug id", () => {
    const md = "# A\n\ntext\n\n## B\n\n### C\n\n#### D (ignored)"
    expect(extractToc(md)).toEqual([
      { id: "a", text: "A", level: 1 },
      { id: "b", text: "B", level: 2 },
      { id: "c", text: "C", level: 3 },
    ])
  })

  it("disambiguates duplicate headings with a counter", () => {
    const md = "## Notes\n\n## Notes"
    expect(extractToc(md).map((e) => e.id)).toEqual(["notes", "notes-1"])
  })

  it("returns an empty list when there are no headings", () => {
    expect(extractToc("just a paragraph")).toEqual([])
  })
})
