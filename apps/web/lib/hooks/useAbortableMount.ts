"use client"
import { useEffect, useRef, type MutableRefObject } from "react"

export type UseAbortableMount = {
  mountedRef: MutableRefObject<boolean>
  abortRef: MutableRefObject<AbortController | null>
}

// Pairs an `unmounted` flag with an in-flight AbortController so callers can
// cancel pending fetches and suppress setState after the component unmounts.
export function useAbortableMount(): UseAbortableMount {
  const mountedRef = useRef(true)
  const abortRef = useRef<AbortController | null>(null)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      // Intentionally read the current value at unmount — the controller may
      // have been replaced after this effect ran, and we want to abort
      // whichever request is in flight right now.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      abortRef.current?.abort()
    }
  }, [])
  return { mountedRef, abortRef }
}
