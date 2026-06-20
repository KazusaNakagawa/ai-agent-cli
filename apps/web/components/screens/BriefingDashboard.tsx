"use client"
import { useCallback, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"
import remarkGfm from "remark-gfm"

import {
  BriefingFile,
  BriefingFileResponse,
  BriefingListResponse,
  BRIEFING_TYPE_LABELS,
} from "@/lib/briefing-types"
import { cn } from "@/lib/utils"

export function BriefingDashboard() {
  const [files, setFiles] = useState<BriefingFile[] | null>(null)
  const [selected, setSelected] = useState<BriefingFile | null>(null)
  const [content, setContent] = useState<string | null>(null)
  const [loadingContent, setLoadingContent] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [contentError, setContentError] = useState<string | null>(null)

  // In-memory cache so revisiting a row is instant (no re-fetch).
  const contentCache = useRef(new Map<string, string>())
  // Tracks the most recently requested file to discard stale responses.
  const latestFile = useRef<string | null>(null)

  const fetchContent = useCallback((file: BriefingFile) => {
    const cached = contentCache.current.get(file.name)
    if (cached !== undefined) {
      setSelected(file)
      setContent(cached)
      setLoadingContent(false)
      return
    }
    latestFile.current = file.name
    setSelected(file)
    setLoadingContent(true)
    setContent(null)
    setContentError(null)
    fetch(`/api/briefing/${encodeURIComponent(file.name)}`, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<BriefingFileResponse>
      })
      .then((data) => {
        contentCache.current.set(file.name, data.content)
        if (latestFile.current === file.name) {
          setContent(data.content)
          setLoadingContent(false)
        }
      })
      .catch((e) => {
        if (latestFile.current === file.name) {
          setContentError(String(e))
          setLoadingContent(false)
        }
      })
  }, [])

  // Fire-and-forget prefetch on hover; silently populates the cache.
  const prefetch = useCallback((file: BriefingFile) => {
    if (contentCache.current.has(file.name)) return
    fetch(`/api/briefing/${encodeURIComponent(file.name)}`, { cache: "no-store" })
      .then((res) => (res.ok ? (res.json() as Promise<BriefingFileResponse>) : null))
      .then((data) => {
        if (data) contentCache.current.set(file.name, data.content)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    let cancelled = false
    fetch("/api/briefing", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<BriefingListResponse>
      })
      .then((data) => {
        if (cancelled) return
        setFiles(data.files)
        if (data.files.length > 0) {
          // Start content fetch immediately — no intermediate state-cycle delay.
          fetchContent(data.files[0])
        }
      })
      .catch((e) => {
        if (!cancelled) setListError(String(e))
      })
    return () => {
      cancelled = true
    }
  }, [fetchContent])

  if (listError) {
    return (
      <p data-testid="briefing-error" className="text-sm text-destructive">
        Failed to load briefings: {listError}
      </p>
    )
  }

  if (files === null) {
    return (
      <p data-testid="briefing-loading" className="text-sm text-muted-foreground">
        Loading briefings…
      </p>
    )
  }

  if (files.length === 0) {
    return (
      <p data-testid="briefing-empty" className="text-sm text-muted-foreground">
        No briefing files found.
      </p>
    )
  }

  return (
    <div data-testid="briefing-dashboard" className="flex h-full gap-4">
      {/* File list */}
      <aside className="w-64 shrink-0 overflow-y-auto rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Date</th>
            </tr>
          </thead>
          <tbody>
            {files.map((file) => (
              <tr
                key={file.name}
                data-testid={`briefing-row-${file.name}`}
                onClick={() => fetchContent(file)}
                onMouseEnter={() => prefetch(file)}
                className={cn(
                  "cursor-pointer border-b text-xs transition-colors last:border-0",
                  selected?.name === file.name
                    ? "bg-accent font-medium text-accent-foreground"
                    : "hover:bg-accent/50",
                )}
              >
                <td className="max-w-[120px] truncate px-3 py-2" title={file.name}>
                  {file.name}
                </td>
                <td className="px-3 py-2">{BRIEFING_TYPE_LABELS[file.type]}</td>
                <td className="px-3 py-2 tabular-nums">{file.date}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </aside>

      {/* Markdown detail */}
      <main className="min-w-0 flex-1 overflow-y-auto">
        {loadingContent ? (
          <p data-testid="briefing-content-loading" className="text-sm text-muted-foreground">
            Loading…
          </p>
        ) : contentError !== null ? (
          <p data-testid="briefing-content-error" className="text-sm text-destructive">
            Failed to load content: {contentError}
          </p>
        ) : content !== null ? (
          <div
            data-testid="briefing-content"
            className="prose prose-sm max-w-none dark:prose-invert"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
              {content}
            </ReactMarkdown>
          </div>
        ) : null}
      </main>
    </div>
  )
}
