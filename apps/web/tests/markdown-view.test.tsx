import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { MarkdownView } from "@/components/ui/MarkdownView"

vi.mock("@/components/ui/MermaidBlock", () => ({
  MermaidBlock: ({ code }: { code: string }) => (
    <div data-testid="mermaid-block">{code}</div>
  ),
}))

describe("MarkdownView", () => {
  it("calls onLinkClick and prevents default navigation when the handler reports it handled the link (success)", async () => {
    const user = userEvent.setup()
    const onLinkClick = vi.fn().mockReturnValue(true)
    render(<MarkdownView content="[go](./other.md)" onLinkClick={onLinkClick} />)

    const link = screen.getByRole("link", { name: "go" })
    await user.click(link)

    expect(onLinkClick).toHaveBeenCalledWith("./other.md")
  })

  it("falls back to default target=_blank behavior when onLinkClick reports it did not handle the link (failure)", () => {
    const onLinkClick = vi.fn().mockReturnValue(false)
    render(<MarkdownView content="[ext](https://example.com)" onLinkClick={onLinkClick} />)

    const link = screen.getByRole("link", { name: "ext" })
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("renders links with default target=_blank behavior when no onLinkClick is passed (boundary)", () => {
    render(<MarkdownView content="[ext](https://example.com)" />)
    const link = screen.getByRole("link", { name: "ext" })
    expect(link).toHaveAttribute("target", "_blank")
  })

  it("does not call onLinkClick for a cmd/ctrl-clicked link, letting the browser open a new tab (boundary)", () => {
    const onLinkClick = vi.fn().mockReturnValue(true)
    render(<MarkdownView content="[go](./other.md)" onLinkClick={onLinkClick} />)

    const link = screen.getByRole("link", { name: "go" })
    fireEvent.click(link, { ctrlKey: true })

    expect(onLinkClick).not.toHaveBeenCalled()
  })

  it("delegates ```mermaid fenced code blocks to MermaidBlock (boundary)", () => {
    render(<MarkdownView content={"```mermaid\nflowchart TB\n  A --> B\n```"} />)

    const block = screen.getByTestId("mermaid-block")
    expect(block).toHaveTextContent("flowchart TB")
    expect(block).toHaveTextContent("A --> B")
  })

  it("renders non-mermaid fenced code blocks as plain code, not MermaidBlock (boundary)", () => {
    render(<MarkdownView content={"```ts\nconst a = 1\n```"} />)

    expect(screen.queryByTestId("mermaid-block")).not.toBeInTheDocument()
    expect(screen.getByText("const a = 1")).toBeInTheDocument()
  })
})
