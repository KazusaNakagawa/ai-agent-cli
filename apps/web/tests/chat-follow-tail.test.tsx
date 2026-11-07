import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ChatMessageList } from "@/components/chat/ChatMessageList"
import type { ChatMessage } from "@/lib/chatStore"

const CLIENT_HEIGHT = 500

function setup(initial: ChatMessage[], fill = true) {
  const list = (messages: ChatMessage[]) => (
    <ChatMessageList
      messages={messages}
      busy={false}
      retrying={false}
      notionReady={false}
      notionState={{}}
      onNotionSave={() => {}}
      fill={fill}
    />
  )
  // jsdom has no layout, so the test owns the content height the hook reads.
  let contentHeight = 0
  const { rerender } = render(list(initial))
  const log = screen.getByTestId("chat-log")
  Object.defineProperty(log, "clientHeight", { value: CLIENT_HEIGHT })
  Object.defineProperty(log, "scrollHeight", { get: () => contentHeight })
  return {
    log,
    update(messages: ChatMessage[], height: number) {
      contentHeight = height
      rerender(list(messages))
    },
    scrollTo(top: number) {
      log.scrollTop = top
      fireEvent.scroll(log)
    },
  }
}

const user = (content: string): ChatMessage => ({ role: "user", content })
const assistant = (content: string): ChatMessage => ({ role: "assistant", content })

describe("chat log follows the tail", () => {
  it("scrolls to the bottom as a reply grows", () => {
    const { log, update } = setup([user("q")])
    update([user("q"), assistant("a")], 1000)
    expect(log.scrollTop).toBe(1000)
    update([user("q"), assistant("a more")], 2000)
    expect(log.scrollTop).toBe(2000)
  })

  it("follows in a host that caps the log height too", () => {
    const { log, update } = setup([user("q")], false)
    update([user("q"), assistant("a")], 1000)
    expect(log.scrollTop).toBe(1000)
  })

  it("lands at the bottom when a long history is restored", () => {
    const { log, update } = setup([])
    update([user("q"), assistant("a"), user("q2"), assistant("a2")], 3000)
    expect(log.scrollTop).toBe(3000)
  })

  it("does nothing while the log is empty", () => {
    const { log, update } = setup([])
    update([], 0)
    expect(log.scrollTop).toBe(0)
  })

  it("stays put after the reader scrolls up", () => {
    const { log, update, scrollTo } = setup([user("q")])
    update([user("q"), assistant("a")], 2000)
    scrollTo(300)
    update([user("q"), assistant("a more")], 3000)
    expect(log.scrollTop).toBe(300)
  })

  it("resumes once the reader returns to the bottom", () => {
    const { log, update, scrollTo } = setup([user("q")])
    update([user("q"), assistant("a")], 2000)
    scrollTo(300)
    scrollTo(1500)
    update([user("q"), assistant("a more")], 3000)
    expect(log.scrollTop).toBe(3000)
  })

  it("treats a position at the threshold as the bottom", () => {
    const { log, update, scrollTo } = setup([user("q")])
    update([user("q"), assistant("a")], 2000)
    scrollTo(2000 - CLIENT_HEIGHT - 40)
    update([user("q"), assistant("a more")], 3000)
    expect(log.scrollTop).toBe(3000)
  })

  it("pauses one pixel past the threshold", () => {
    const { log, update, scrollTo } = setup([user("q")])
    update([user("q"), assistant("a")], 2000)
    const top = 2000 - CLIENT_HEIGHT - 41
    scrollTo(top)
    update([user("q"), assistant("a more")], 3000)
    expect(log.scrollTop).toBe(top)
  })

  it("jumps to the bottom on a new question even when scrolled up", () => {
    const { log, update, scrollTo } = setup([user("q")])
    update([user("q"), assistant("a")], 2000)
    scrollTo(300)
    update([user("q"), assistant("a"), user("next")], 2200)
    expect(log.scrollTop).toBe(2200)
  })
})
