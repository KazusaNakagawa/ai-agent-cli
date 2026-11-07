import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useSpeechRecognition } from "@/lib/hooks/useSpeechRecognition"

type Results = { transcript: string }[][]

// Like Chrome, stop() does not end the session synchronously: results and
// onend can still arrive afterwards, which the tests fire by hand.
class FakeRecognition {
  static instances: FakeRecognition[] = []
  lang = ""
  continuous = false
  interimResults = false
  onresult: ((e: { results: Results }) => void) | null = null
  onend: (() => void) | null = null
  onerror: ((e: { error: string }) => void) | null = null
  stopped = false
  start() {
    FakeRecognition.instances.push(this)
  }
  stop() {
    this.stopped = true
  }
  emit(...transcripts: string[]) {
    this.onresult?.({ results: transcripts.map((t) => [{ transcript: t }]) })
  }
}

function setup() {
  const onTranscript = vi.fn()
  const hook = renderHook(() => useSpeechRecognition({ onTranscript }))
  return { onTranscript, hook }
}

describe("useSpeechRecognition stop()", () => {
  beforeEach(() => {
    FakeRecognition.instances = []
    vi.stubGlobal("SpeechRecognition", FakeRecognition)
  })
  afterEach(() => vi.unstubAllGlobals())

  it("ignores results that arrive after stop()", () => {
    const { onTranscript, hook } = setup()
    act(() => hook.result.current.toggle(""))
    const rec = FakeRecognition.instances[0]
    act(() => rec.emit("sent text"))
    expect(onTranscript).toHaveBeenLastCalledWith("sent text")

    act(() => hook.result.current.stop())
    act(() => rec.emit("sent text"))
    expect(onTranscript).toHaveBeenCalledTimes(1)
    expect(rec.stopped).toBe(true)
  })

  it("shows the mic as idle right away", () => {
    const { hook } = setup()
    act(() => hook.result.current.toggle(""))
    expect(hook.result.current.listening).toBe(true)
    act(() => hook.result.current.stop())
    expect(hook.result.current.listening).toBe(false)
  })

  it("starts a fresh session afterwards, appended to the new prefix", () => {
    const { onTranscript, hook } = setup()
    act(() => hook.result.current.toggle(""))
    const first = FakeRecognition.instances[0]
    act(() => first.emit("old"))
    act(() => hook.result.current.stop())

    act(() => hook.result.current.toggle("typed"))
    const second = FakeRecognition.instances[1]
    expect(second).not.toBe(first)
    act(() => second.emit("new"))
    expect(onTranscript).toHaveBeenLastCalledWith("typed new")

    // The stopped session's late events touch neither the text nor the state.
    act(() => first.emit("old"))
    act(() => first.onend?.())
    expect(onTranscript).toHaveBeenLastCalledWith("typed new")
    expect(hook.result.current.listening).toBe(true)
  })

  it("does nothing when the mic is already off", () => {
    const { onTranscript, hook } = setup()
    act(() => hook.result.current.stop())
    expect(hook.result.current.listening).toBe(false)
    expect(onTranscript).not.toHaveBeenCalled()
    expect(FakeRecognition.instances).toHaveLength(0)
  })

  it("still toggles off the way it did before", () => {
    const { hook } = setup()
    act(() => hook.result.current.toggle(""))
    const rec = FakeRecognition.instances[0]
    act(() => hook.result.current.toggle(""))
    expect(rec.stopped).toBe(true)
    act(() => rec.onend?.())
    expect(hook.result.current.listening).toBe(false)
  })
})
