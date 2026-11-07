import { act, fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { useFollowTail, type FollowTailOptions } from "@/lib/hooks/useFollowTail"

type Msg = { role: "user" | "assistant"; content: string }
const CLIENT_HEIGHT = 500

let api: ReturnType<typeof useFollowTail>

function Log({ messages, options }: { messages: Msg[]; options?: FollowTailOptions }) {
  api = useFollowTail(messages, options)
  return <div ref={api.ref} onScroll={api.onScroll} data-testid="log" />
}

function setup(initial: Msg[], options?: FollowTailOptions, initialHeight = 0) {
  let height = initialHeight
  const { rerender } = render(<Log messages={initial} options={options} />)
  const log = screen.getByTestId("log")
  Object.defineProperty(log, "clientHeight", { value: CLIENT_HEIGHT })
  Object.defineProperty(log, "scrollHeight", { get: () => height })
  return {
    log,
    update(messages: Msg[], h: number) {
      height = h
      rerender(<Log messages={messages} options={options} />)
    },
    scrollTo(top: number) {
      log.scrollTop = top
      fireEvent.scroll(log)
    },
  }
}

const user = (c: string): Msg => ({ role: "user", content: c })
const assistant = (c: string): Msg => ({ role: "assistant", content: c })
const JOURNAL: FollowTailOptions = { followFromStart: false, followOnNewUserMessage: false }

describe("useFollowTail options", () => {
  it("stays at the top until told to follow", () => {
    const { log, update } = setup([], JOURNAL)
    update([user("q"), assistant("a")], 2000)
    expect(log.scrollTop).toBe(0)
  })

  it("ignores a new user message when that trigger is off", () => {
    const { log, update } = setup([user("q")], JOURNAL)
    update([user("q"), assistant("a"), user("q2")], 2000)
    expect(log.scrollTop).toBe(0)
  })

  it("follows growth once follow() is called", () => {
    const { log, update } = setup([], JOURNAL, 800)
    act(() => api.follow())
    expect(log.scrollTop).toBe(800)
    update([user("q"), assistant("a")], 2000)
    expect(log.scrollTop).toBe(2000)
  })

  it("pauses when scrolled up and resumes at the bottom", () => {
    const { log, update, scrollTo } = setup([], JOURNAL)
    act(() => api.follow())
    update([user("q"), assistant("a")], 2000)
    scrollTo(300)
    update([user("q"), assistant("a more")], 3000)
    expect(log.scrollTop).toBe(300)
    scrollTo(3000 - CLIENT_HEIGHT)
    update([user("q"), assistant("a even more")], 4000)
    expect(log.scrollTop).toBe(4000)
  })

  it("stops following after stopFollowing()", () => {
    const { log, update } = setup([], JOURNAL)
    act(() => api.follow())
    update([user("q"), assistant("a")], 2000)
    act(() => api.stopFollowing())
    update([user("q"), assistant("a more")], 3000)
    expect(log.scrollTop).toBe(2000)
  })

  it("keeps the chat defaults: follows from the start and on a new question", () => {
    const { log, update, scrollTo } = setup([user("q")])
    update([user("q"), assistant("a")], 2000)
    expect(log.scrollTop).toBe(2000)
    scrollTo(300)
    update([user("q"), assistant("a"), user("q2")], 2500)
    expect(log.scrollTop).toBe(2500)
  })
})
