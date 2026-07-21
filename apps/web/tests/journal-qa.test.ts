import { describe, expect, it } from "vitest"

import { AI_LABEL, formatQaBlock, USER_LABEL } from "@/lib/journalQa"

describe("formatQaBlock", () => {
  it("labels the question and answer with their roles", () => {
    const block = formatQaBlock("What next?", "Focus on tests.")
    expect(block).toBe("**You:**\n\nWhat next?\n\n**AI:**\n\nFocus on tests.")
  })

  it("keeps multi-line markdown answers intact", () => {
    const answer = "- point one\n- point two"
    const block = formatQaBlock("q", answer)
    expect(block).toContain(`${AI_LABEL}\n\n${answer}`)
    expect(block.startsWith(USER_LABEL)).toBe(true)
  })
})
