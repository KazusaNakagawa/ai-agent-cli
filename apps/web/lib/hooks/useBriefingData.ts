import { useCallback, useEffect, useRef, useState } from "react"

import {
  BriefingFile,
  BriefingFileResponse,
  BriefingListResponse,
} from "@/lib/briefing-types"

function contentUrl(name: string): string {
  return `/api/briefing/${encodeURIComponent(name)}`
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export interface BriefingData {
  files: BriefingFile[] | null
  selected: BriefingFile | null
  content: string | null
  loadingContent: boolean
  listError: string | null
  contentError: string | null
  fetchContent: (file: BriefingFile) => void
  prefetch: (file: BriefingFile) => void
  /**
   * Re-read `name` from disk if it is the file currently on screen, dropping
   * its cache entry first. No-op for any other file. Used after something
   * appends to the open document (Issue #436).
   */
  refreshContent: (name: string) => void
  close: () => void
}

/**
 * Owns all briefing data fetching: the file list, per-file markdown content,
 * an in-memory content cache, hover prefetch, and stale-response protection.
 */
export function useBriefingData(): BriefingData {
  const [files, setFiles] = useState<BriefingFile[] | null>(null)
  const [selected, setSelected] = useState<BriefingFile | null>(null)
  const [content, setContent] = useState<string | null>(null)
  const [loadingContent, setLoadingContent] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [contentError, setContentError] = useState<string | null>(null)

  const contentCache = useRef(new Map<string, string>())
  const latestFile = useRef<string | null>(null)

  const fetchContent = useCallback((file: BriefingFile) => {
    latestFile.current = file.name
    setSelected(file)

    const cached = contentCache.current.get(file.name)
    if (cached !== undefined) {
      setContent(cached)
      setLoadingContent(false)
      setContentError(null)
      return
    }

    setLoadingContent(true)
    setContent(null)
    setContentError(null)
    fetchJson<BriefingFileResponse>(contentUrl(file.name))
      .then((data) => {
        contentCache.current.set(file.name, data.content)
        if (latestFile.current !== file.name) return
        setContent(data.content)
        setLoadingContent(false)
      })
      .catch((e) => {
        if (latestFile.current !== file.name) return
        setContentError(String(e))
        setLoadingContent(false)
      })
  }, [])

  const prefetch = useCallback((file: BriefingFile) => {
    if (contentCache.current.has(file.name)) return
    fetchJson<BriefingFileResponse>(contentUrl(file.name))
      .then((data) => contentCache.current.set(file.name, data.content))
      .catch(() => {})
  }, [])

  const refreshContent = useCallback((name: string) => {
    // Only the file on screen is worth re-reading; an append to anything else
    // is picked up the next time that file is opened.
    if (latestFile.current !== name) return
    contentCache.current.delete(name)
    // Deliberately no `setLoadingContent(true)`: that swaps the rendered body
    // for the loading placeholder, which unmounts the scroll container and
    // throws the reader back to the top. The stale text stays visible for the
    // one round trip instead.
    fetchJson<BriefingFileResponse>(contentUrl(name))
      .then((data) => {
        contentCache.current.set(name, data.content)
        if (latestFile.current !== name) return
        setContent(data.content)
        setContentError(null)
      })
      .catch(() => {
        // Best-effort, like prefetch: a failed background refresh must not
        // replace what the user is reading with an error. The cache entry is
        // already gone, so the next open re-reads from disk.
      })
  }, [])

  const close = useCallback(() => {
    latestFile.current = null
    setSelected(null)
    setContent(null)
    setContentError(null)
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchJson<BriefingListResponse>("/api/briefing")
      .then((data) => {
        if (!cancelled) setFiles(data.files)
      })
      .catch((e) => {
        if (!cancelled) setListError(String(e))
      })
    return () => {
      cancelled = true
    }
  }, [])

  return {
    files,
    selected,
    content,
    loadingContent,
    listError,
    contentError,
    fetchContent,
    prefetch,
    refreshContent,
    close,
  }
}
