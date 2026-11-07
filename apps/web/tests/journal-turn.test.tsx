import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { JournalTurn } from "@/components/journal/JournalTurn"

describe("JournalTurn", () => {
  it("shows the question as a right-aligned bubble", () => {
    render(<JournalTurn question="what next?" answer="plan it" />)
    const bubble = screen.getByTestId("journal-turn-question")
    expect(bubble).toHaveTextContent("what next?")
    expect(bubble).toHaveClass("self-end", "rounded-2xl", "bg-muted")
  })

  it("shows the answer as plain text with no frame", () => {
    render(<JournalTurn question="q" answer="plain **answer**" />)
    const answer = screen.getByTestId("journal-turn-answer")
    expect(answer).toHaveTextContent("plain answer")
    expect(answer).not.toHaveClass("border")
    expect(answer).not.toHaveClass("rounded-2xl")
    expect(answer.querySelector(".border")).toBeNull()
  })

  it("shows the thinking indicator while the answer is pending", () => {
    render(<JournalTurn question="q" answer={null} />)
    expect(screen.getByTestId("journal-chat-thinking")).toBeInTheDocument()
    expect(screen.queryByTestId("journal-turn-answer")).toBeNull()
  })

  it("omits the answer for a question that never got one", () => {
    render(<JournalTurn question="q" answer="" />)
    expect(screen.queryByTestId("journal-turn-answer")).toBeNull()
    expect(screen.queryByTestId("journal-chat-thinking")).toBeNull()
  })
})
