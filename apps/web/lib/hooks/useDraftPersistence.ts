"use client"
import { useEffect, useState } from "react"

type Options = {
  // Bumped if the persisted shape changes incompatibly.
  storageKey: string
}

export type UseDraftPersistence = {
  draft: string
  setDraft: (value: string) => void
  hydrated: boolean
}

// Render "" on first paint so SSR and the first client render agree
// (sessionStorage is unavailable on the server). After mount the hook
// promotes draft to whatever was persisted in this tab.
export function useDraftPersistence({ storageKey }: Options): UseDraftPersistence {
  const [draft, setDraft] = useState("")
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        setDraft(window.sessionStorage.getItem(storageKey) ?? "")
      } catch {
        // sessionStorage unavailable — keep the empty initial.
      }
    }
    setHydrated(true)
  }, [storageKey])

  useEffect(() => {
    if (!hydrated) return
    if (typeof window === "undefined") return
    try {
      if (draft === "") {
        window.sessionStorage.removeItem(storageKey)
      } else {
        window.sessionStorage.setItem(storageKey, draft)
      }
    } catch {
      // quota / unavailable — draft remains in memory for the tab
    }
  }, [draft, hydrated, storageKey])

  return { draft, setDraft, hydrated }
}
