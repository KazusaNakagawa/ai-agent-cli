import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { createJobStoreProvider, type WatchCtx } from "@/lib/createJobStoreProvider"

// Minimal non-/run consumer: a fake "chat-like" store with a different state
// shape. Exercises the factory's lifecycle scaffolding (sessionStorage hydrate,
// watch loop, jobId-bound dispatches, reset) without depending on /run.

type FakeStatus = "idle" | "running" | "done" | "failed"

type FakeState = {
  jobId: string | null
  status: FakeStatus
  events: string[]
  error: string | null
}

const STORAGE_KEY = "test:fake-store:v1"

const initialState: FakeState = {
  jobId: null,
  status: "idle",
  events: [],
  error: null,
}

function makeStore(opts: {
  watch: (
    jobId: string,
    ctx: { signal: AbortSignal; setState: (m: (s: FakeState) => FakeState) => void },
  ) => Promise<void>
  start?: (
    jobId: string,
    ctx: { setState: (m: (s: FakeState) => FakeState) => void },
  ) => Promise<void>
}) {
  return createJobStoreProvider<FakeState, { jobId: string }>({
    storageKey: STORAGE_KEY,
    initialState,
    getJobId: (s) => s.jobId,
    isInFlight: (s) => s.status === "running",
    isPersistable: (s) => Boolean(s.jobId) || Boolean(s.error),
    start: async ({ jobId }, ctx) => {
      ctx.setState(() => ({ ...initialState, jobId, status: "running" }))
      if (opts.start) await opts.start(jobId, ctx)
    },
    watch: opts.watch,
  })
}

function Probe({ useStore }: { useStore: () => FakeState & { startJob: (o: { jobId: string }) => Promise<void>; reset: () => void; isBackgrounded: boolean } }) {
  const s = useStore()
  return (
    <div>
      <div data-testid="jobId">{s.jobId ?? ""}</div>
      <div data-testid="status">{s.status}</div>
      <div data-testid="events">{s.events.join(",")}</div>
      <div data-testid="error">{s.error ?? ""}</div>
      <div data-testid="bg">{s.isBackgrounded ? "yes" : "no"}</div>
      <button data-testid="start" onClick={() => s.startJob({ jobId: "new-1" })}>start</button>
      <button data-testid="reset" onClick={s.reset}>reset</button>
    </div>
  )
}

describe("createJobStoreProvider — generic lifecycle", () => {
  beforeEach(() => {
    sessionStorage.clear()
  })
  afterEach(() => {
    sessionStorage.clear()
    vi.useRealTimers()
  })

  it("hydrates a persisted in-flight snapshot and triggers the watch loop", async () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ jobId: "resume-1", status: "running", events: ["a"], error: null }),
    )
    const watch = vi.fn(async (_jobId: string, { setState }: WatchCtx<FakeState>) => {
      setState((prev) => ({ ...prev, events: [...prev.events, "b"], status: "done" }))
    })
    const { Provider, useStore } = makeStore({ watch })

    render(
      <Provider>
        <Probe useStore={useStore} />
      </Provider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("done")
    })
    expect(watch).toHaveBeenCalledTimes(1)
    expect(watch.mock.calls[0][0]).toBe("resume-1")
    expect(screen.getByTestId("events")).toHaveTextContent("a,b")
  })

  it("does not run watch for a hydrated terminal snapshot", async () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ jobId: "done-1", status: "done", events: ["x"], error: null }),
    )
    const watch = vi.fn(async () => {})
    const { Provider, useStore } = makeStore({ watch })

    render(
      <Provider>
        <Probe useStore={useStore} />
      </Provider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("done")
    })
    await new Promise((r) => setTimeout(r, 20))
    expect(watch).not.toHaveBeenCalled()
  })

  it("drops an unresumable snapshot (in-flight with no jobId) on hydrate", async () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ jobId: null, status: "running", events: [], error: null }),
    )
    const watch = vi.fn(async () => {})
    const { Provider, useStore } = makeStore({ watch })

    render(
      <Provider>
        <Probe useStore={useStore} />
      </Provider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("idle")
    })
    expect(screen.getByTestId("jobId")).toHaveTextContent("")
    expect(watch).not.toHaveBeenCalled()
  })

  it("ignores late watch dispatches after the jobId has changed", async () => {
    let releaseFirstWatch: (() => void) | null = null
    const firstWatchStarted = new Promise<void>((resolve) => {
      releaseFirstWatch = resolve
    })

    const watch = vi.fn(async (jobId: string, { signal, setState }: WatchCtx<FakeState>) => {
      if (jobId === "resume-1") {
        // Wait until we've swapped to a new jobId, then try to write — the
        // factory's bound setState must drop this update.
        await firstWatchStarted
        if (signal.aborted) return
        setState((prev) => ({ ...prev, events: [...prev.events, "stale!"] }))
        return
      }
      setState((prev) => ({ ...prev, status: "done", events: [...prev.events, "fresh"] }))
    })

    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ jobId: "resume-1", status: "running", events: [], error: null }),
    )
    const { Provider, useStore } = makeStore({ watch })

    render(
      <Provider>
        <Probe useStore={useStore} />
      </Provider>,
    )

    await waitFor(() => expect(watch).toHaveBeenCalledTimes(1))

    // Swap to a new jobId via startJob; this aborts the first watch and starts
    // a new one. After the new one runs, release the first so it tries (and
    // should fail) to write back.
    await act(async () => {
      screen.getByTestId("start").click()
    })

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("done")
    })
    await act(async () => {
      releaseFirstWatch?.()
      // Give the first watch a chance to dispatch.
      await new Promise((r) => setTimeout(r, 10))
    })

    // "stale!" must NOT appear — the bound setState dropped it.
    expect(screen.getByTestId("events")).toHaveTextContent("fresh")
    expect(screen.getByTestId("events")).not.toHaveTextContent("stale!")
  })

  it("clears persisted state on reset()", async () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ jobId: "live-1", status: "done", events: ["a"], error: null }),
    )
    const watch = vi.fn(async () => {})
    const { Provider, useStore } = makeStore({ watch })

    render(
      <Provider>
        <Probe useStore={useStore} />
      </Provider>,
    )

    await waitFor(() => expect(screen.getByTestId("jobId")).toHaveTextContent("live-1"))

    await act(async () => {
      screen.getByTestId("reset").click()
    })

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("idle")
    })
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it("applies serializeForStorage so UI-only fields don't survive a reload", async () => {
    // A minimal store that surfaces an in-memory `transient` flag but strips
    // it before persisting — mirrors the `sessionExpired` contract on /run.
    type S = { jobId: string | null; transient: boolean; persistedNote: string }
    const KEY = "test:serialize:v1"
    const init: S = { jobId: null, transient: false, persistedNote: "" }
    sessionStorage.clear()
    const { Provider, useStore } = createJobStoreProvider<S, void>({
      storageKey: KEY,
      initialState: init,
      getJobId: (s) => s.jobId,
      isInFlight: () => false,
      isPersistable: (s) => Boolean(s.jobId) || Boolean(s.persistedNote),
      serializeForStorage: (s) => ({ ...s, transient: false }),
      start: async (_opts, { setState }) => {
        setState(() => ({ jobId: "kept", transient: true, persistedNote: "saved" }))
      },
      watch: async () => {},
    })

    function P() {
      const s = useStore()
      return (
        <div>
          <button data-testid="go" onClick={() => s.startJob()}>go</button>
          <div data-testid="transient">{String(s.transient)}</div>
        </div>
      )
    }

    render(
      <Provider>
        <P />
      </Provider>,
    )
    await act(async () => {
      screen.getByTestId("go").click()
    })

    // In-memory: transient flag survives.
    await waitFor(() => {
      expect(screen.getByTestId("transient")).toHaveTextContent("true")
    })
    // On-disk: transient was stripped to false.
    const raw = sessionStorage.getItem(KEY)
    expect(raw).not.toBeNull()
    const stored = JSON.parse(raw as string)
    expect(stored.jobId).toBe("kept")
    expect(stored.persistedNote).toBe("saved")
    expect(stored.transient).toBe(false)
    sessionStorage.clear()
  })

  it("aborts the watch when the provider unmounts mid-flight", async () => {
    let abortedFlag = false
    const watch = vi.fn(async (_jobId: string, { signal }: WatchCtx<FakeState>) => {
      await new Promise<void>((resolve) => {
        signal.addEventListener("abort", () => {
          abortedFlag = true
          resolve()
        })
      })
    })
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ jobId: "live", status: "running", events: [], error: null }),
    )
    const { Provider, useStore } = makeStore({ watch })

    const { unmount } = render(
      <Provider>
        <Probe useStore={useStore} />
      </Provider>,
    )

    await waitFor(() => expect(watch).toHaveBeenCalledTimes(1))
    unmount()
    await waitFor(() => expect(abortedFlag).toBe(true))
  })

  it("useStore throws when used outside Provider", () => {
    const { useStore } = makeStore({ watch: async () => {} })
    function Bad() {
      useStore()
      return null
    }
    // Suppress React's expected error log for the failing render.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {})
    try {
      expect(() => render(<Bad />)).toThrow(/createJobStoreProvider/)
    } finally {
      spy.mockRestore()
    }
  })
})
