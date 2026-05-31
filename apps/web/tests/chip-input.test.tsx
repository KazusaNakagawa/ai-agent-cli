import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ChipInput } from "@/components/ChipInput"

describe("ChipInput", () => {
  it("adds a chip on Enter", async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <ChipInput
        values={[]}
        onChange={onChange}
        testid="t"
        normalise={(s) => s.toUpperCase()}
      />,
    )
    const input = screen.getByTestId("t-draft")
    await user.type(input, "pltr{Enter}")
    expect(onChange).toHaveBeenLastCalledWith(["PLTR"])
  })

  it("adds a chip on comma", async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ChipInput values={[]} onChange={onChange} testid="t" />)
    await user.type(screen.getByTestId("t-draft"), "AI規制,")
    expect(onChange).toHaveBeenLastCalledWith(["AI規制"])
  })

  it("removes a chip via the × button", async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <ChipInput
        values={["PLTR", "NVDA"]}
        onChange={onChange}
        testid="t"
      />,
    )
    await user.click(screen.getByTestId("t-remove-0"))
    expect(onChange).toHaveBeenLastCalledWith(["NVDA"])
  })

  it("removes the last chip when Backspace is pressed on empty input", async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <ChipInput values={["PLTR", "NVDA"]} onChange={onChange} testid="t" />,
    )
    const input = screen.getByTestId("t-draft")
    input.focus()
    await user.keyboard("{Backspace}")
    expect(onChange).toHaveBeenLastCalledWith(["PLTR"])
  })

  it("ignores duplicates", async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <ChipInput
        values={["PLTR"]}
        onChange={onChange}
        testid="t"
        normalise={(s) => s.toUpperCase()}
      />,
    )
    await user.type(screen.getByTestId("t-draft"), "pltr{Enter}")
    expect(onChange).not.toHaveBeenCalled()
  })
})
