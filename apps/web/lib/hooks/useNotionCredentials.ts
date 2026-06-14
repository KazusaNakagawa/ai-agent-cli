"use client"
import { useEffect, useState } from "react"

export type UseNotionCredentials = {
  notionReady: boolean
  // false until /api/credentials answers — the consumer should keep its
  // Notion controls disabled while this is false (no premature enable).
  hydrated: boolean
}

export function useNotionCredentials(): UseNotionCredentials {
  const [creds, setCreds] = useState<Record<string, boolean> | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch("/api/credentials", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: Record<string, boolean> | null) => {
        if (cancelled) return
        setCreds(data ?? {})
      })
      .catch(() => {
        // Network failure — leave creds null so the gate stays closed
        // rather than enabling controls on incomplete information.
      })
    return () => {
      cancelled = true
    }
  }, [])

  return {
    notionReady: Boolean(creds && creds.NOTION_API_KEY && creds.NOTION_DATABASE_ID),
    hydrated: creds !== null,
  }
}
