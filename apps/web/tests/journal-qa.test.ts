import { describe, expect, it } from "vitest"

import { AI_LABEL, formatQaBlock, parseQaTranscript, USER_LABEL } from "@/lib/journalQa"

describe("parseQaTranscript", () => {
  it("splits a multi-turn entry into turns and drops the --- separators (success)", () => {
    const md = [
      "## 22:28:01",
      "",
      formatQaBlock("first\n\n- keep me", "answer one"),
      "",
      "",
      "---",
      "",
      formatQaBlock("second", "answer two"),
    ].join("\n")
    expect(parseQaTranscript(md)).toEqual({
      preamble: "## 22:28:01",
      turns: [
        { question: "first\n\n- keep me", answer: "answer one" },
        { question: "second", answer: "answer two" },
      ],
    })
  })

  it("returns null for a legacy entry without role labels (failure)", () => {
    expect(parseQaTranscript("## 09:00:00\n\njust a note")).toBeNull()
  })

  it("keeps a question with no AI answer yet as an empty answer (boundary)", () => {
    expect(parseQaTranscript(`${USER_LABEL}\n\nonly a question`)?.turns).toEqual([
      { question: "only a question", answer: "" },
    ])
  })
})

describe("role labels inside message bodies", () => {
  it("round-trips a body line that equals a role label without splitting the turn", () => {
    const question = `quote:\n${USER_LABEL}\nend`
    const answer = `  ${AI_LABEL}  \nstill the answer\n${USER_LABEL}`
    expect(parseQaTranscript(formatQaBlock(question, answer))?.turns).toEqual([
      { question, answer: answer.trim() },
    ])
  })

  it("escapes label-only body lines so raw Markdown still renders them literally", () => {
    const block = formatQaBlock(USER_LABEL, AI_LABEL)
    expect(block).toBe("**You:**\n\n\\*\\*You:\\*\\*\n\n**AI:**\n\n\\*\\*AI:\\*\\*")
  })

  it("leaves labels that share a line with other text untouched", () => {
    const block = formatQaBlock(`${USER_LABEL} inline`, "a")
    expect(block).toContain(`${USER_LABEL} inline`)
    expect(parseQaTranscript(block)?.turns).toHaveLength(1)
  })
})

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
