import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { BriefingSearch } from "@/components/briefing/BriefingSearch"

describe("BriefingSearch", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("debounces input before emitting the query", () => {
    const onSearch = vi.fn()
    render(<BriefingSearch onSearch={onSearch} debounceMs={250} />)

    fireEvent.change(screen.getByTestId("briefing-search-input"), { target: { value: "nvda" } })
    onSearch.mockClear()
    act(() => vi.advanceTimersByTime(249))
    expect(onSearch).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1))
    expect(onSearch).toHaveBeenCalledWith("nvda")
  })

  it("clear button resets the input and emits an empty query", () => {
    const onSearch = vi.fn()
    render(<BriefingSearch onSearch={onSearch} debounceMs={250} />)

    fireEvent.change(screen.getByTestId("briefing-search-input"), { target: { value: "nvda" } })
    act(() => vi.advanceTimersByTime(250))

    fireEvent.click(screen.getByTestId("briefing-search-clear"))
    act(() => vi.advanceTimersByTime(250))
    expect(onSearch).toHaveBeenLastCalledWith("")
    expect(screen.getByTestId("briefing-search-input")).toHaveValue("")
  })
})
