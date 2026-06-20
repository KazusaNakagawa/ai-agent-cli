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
    close,
  }
}
