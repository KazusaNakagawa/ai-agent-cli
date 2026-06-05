"use client"
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

/**
 * Generic factory for `/api/...` job-backed React stores.
 *
 * Extracted from `jobStore.tsx` so the chat-flavored store (#125) can layer on
 * the same lifecycle scaffolding — sessionStorage hydration, jobId-bound state
 * updates, AbortController cleanup — without copy-pasting the polling loop.
 *
 * The factory does *not* know the protocol: it only owns the React lifecycle.
 * The caller's ``start`` and ``watch`` callbacks decide how to talk to the
 * backend (HTTP POST + polling for /run, SSE for chat).
 */

export type JobStoreSetState<State> = (mapper: (prev: State) => State) => void

export type StartCtx<State> = {
  signal: AbortSignal
  setState: JobStoreSetState<State>
}

export type WatchCtx<State> = {
  signal: AbortSignal
  /**
   * setState wrapper that no-ops when the caller's `jobId` no longer matches
   * the state's current jobId — protects against late dispatches from a
   * watch loop that has already been superseded by a newer job.
   */
  setState: JobStoreSetState<State>
}

export type JobStoreConfig<State, StartOpts> = {
  /** sessionStorage key. Bump (e.g. ``...v2``) if the persisted shape changes incompatibly. */
  storageKey: string
  initialState: State
  /** Identity of the current job — used to bind watch dispatches and key the watch effect. */
  getJobId: (s: State) => string | null
  /** Whether the state needs the watch lifecycle running. */
  isInFlight: (s: State) => boolean
  /**
   * Whether to persist the current state. Default: persist when a jobId or
   * surfacing-worthy fields exist (caller-defined). When this returns false,
   * the persisted entry is removed instead of overwritten.
   */
  isPersistable: (s: State) => boolean
  /**
   * Whether a hydrated snapshot is unresumable and should be dropped on load
   * (e.g. status=pending without a jobId — nothing to poll). Defaults to
   * "in-flight with no jobId".
   */
  isUnresumable?: (s: State) => boolean
  /**
   * Transform state right before it's serialized to sessionStorage. Use to
   * strip UI-only fields (e.g. transient flags) that must not survive a reload.
   * Defaults to identity.
   */
  serializeForStorage?: (s: State) => State
  /**
   * Kicks the job off. Called from the consumer's startJob callback. Receives
   * a setState that's NOT jobId-bound (the loop hasn't started yet, and the
   * caller is the one assigning the new jobId via setState).
   */
  start: (opts: StartOpts, ctx: StartCtx<State>) => Promise<void>
  /**
   * Runs while a job is in-flight. Caller owns the protocol (polling / SSE /
   * whatever). The provided setState is auto-guarded by the jobId the watch
   * was started with, so a stale callback can't clobber a newer job.
   *
   * Honor ``ctx.signal``: the factory aborts on jobId change, status leaving
   * in-flight, or unmount.
   */
  watch: (jobId: string, ctx: WatchCtx<State>) => Promise<void>
}

export type JobStoreContextValue<State, StartOpts> = State & {
  /** True while the job is in flight (mirror of ``isInFlight(state)``). */
  isBackgrounded: boolean
  startJob: (opts: StartOpts) => Promise<void>
  reset: () => void
}

function loadPersisted<State>(
  storageKey: string,
  initialState: State,
  isUnresumable: (s: State) => boolean,
): State {
  if (typeof window === "undefined") return initialState
  try {
    const raw = window.sessionStorage.getItem(storageKey)
    if (!raw) return initialState
    const parsed = JSON.parse(raw) as Partial<State>
    const next = { ...initialState, ...parsed } as State
    if (isUnresumable(next)) return initialState
    return next
  } catch {
    return initialState
  }
}

function persistTo<State>(storageKey: string, state: State): void {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(storageKey, JSON.stringify(state))
  } catch {
    // quota / unavailable — state remains in memory for the tab
  }
}

function clearPersistedFrom(storageKey: string): void {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.removeItem(storageKey)
  } catch {
    // ignore
  }
}

export type CreatedJobStore<State, StartOpts> = {
  Provider: (props: { children: ReactNode }) => JSX.Element
  useStore: () => JobStoreContextValue<State, StartOpts>
}

export function createJobStoreProvider<State, StartOpts>(
  config: JobStoreConfig<State, StartOpts>,
): CreatedJobStore<State, StartOpts> {
  const {
    storageKey,
    initialState,
    getJobId,
    isInFlight,
    isPersistable,
    isUnresumable = (s) => isInFlight(s) && getJobId(s) === null,
    serializeForStorage = (s) => s,
    start,
    watch,
  } = config

  type Value = JobStoreContextValue<State, StartOpts>
  const Context = createContext<Value | null>(null)

  function Provider({ children }: { children: ReactNode }): JSX.Element {
    // Render initialState on first paint so SSR and the first client render
    // agree (sessionStorage is unavailable on the server). The hydrate effect
    // promotes state to whatever was persisted in this tab.
    const [state, setStateRaw] = useState<State>(initialState)
    const [hydrated, setHydrated] = useState(false)

    useEffect(() => {
      setStateRaw(loadPersisted(storageKey, initialState, isUnresumable))
      setHydrated(true)
    }, [])

    useEffect(() => {
      if (!hydrated) return
      if (isPersistable(state)) {
        persistTo(storageKey, serializeForStorage(state))
      } else {
        clearPersistedFrom(storageKey)
      }
    }, [state, hydrated])

    const jobId = getJobId(state)
    const inFlight = isInFlight(state)

    // Watch lifecycle: runs while an in-flight job with a jobId is present.
    // Aborted/cleaned up on jobId change, status leaving in-flight, or unmount.
    useEffect(() => {
      if (!hydrated) return
      if (!jobId) return
      if (!inFlight) return

      const ctl = new AbortController()
      let stopped = false

      const stop = () => {
        stopped = true
        ctl.abort()
      }

      const boundSetState: JobStoreSetState<State> = (mapper) => {
        if (stopped) return
        setStateRaw((prev) => {
          // jobId changed since this watch started → drop the late dispatch.
          if (getJobId(prev) !== jobId) return prev
          return mapper(prev)
        })
      }

      ;(async () => {
        try {
          await watch(jobId, { signal: ctl.signal, setState: boundSetState })
        } catch {
          // The watch callback owns its own error handling via setState. A
          // raw throw here usually means an abort race — swallow it so the
          // unmount cleanup path stays quiet.
        }
      })()

      return stop
    }, [hydrated, jobId, inFlight])

    const startJob = useCallback(async (opts: StartOpts) => {
      const ctl = new AbortController()
      const unboundSetState: JobStoreSetState<State> = (mapper) => {
        setStateRaw(mapper)
      }
      await start(opts, { signal: ctl.signal, setState: unboundSetState })
    }, [])

    const reset = useCallback(() => {
      setStateRaw(initialState)
      clearPersistedFrom(storageKey)
    }, [])

    const value = useMemo<Value>(
      () => ({
        ...state,
        isBackgrounded: inFlight,
        startJob,
        reset,
      }),
      [state, inFlight, startJob, reset],
    )

    return <Context.Provider value={value}>{children}</Context.Provider>
  }

  function useStore(): Value {
    const ctx = useContext(Context)
    if (!ctx) {
      throw new Error(
        "useStore must be used inside the Provider returned by createJobStoreProvider",
      )
    }
    return ctx
  }

  return { Provider, useStore }
}
