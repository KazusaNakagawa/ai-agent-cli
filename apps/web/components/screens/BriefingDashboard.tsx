"use client"
import { useEffect, useState } from "react"
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
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch("/api/briefing", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<BriefingListResponse>
      })
      .then((data) => {
        setFiles(data.files)
        if (data.files.length > 0) setSelected(data.files[0])
      })
      .catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    if (!selected) return
    let cancelled = false
    setLoadingContent(true)
    setContent(null)
    fetch(`/api/briefing/${encodeURIComponent(selected.name)}`, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<BriefingFileResponse>
      })
      .then((data) => {
        if (!cancelled) setContent(data.content)
      })
      .catch((e) => {
        if (!cancelled) setError(String(e))
      })
      .finally(() => {
        if (!cancelled) setLoadingContent(false)
      })
    return () => {
      cancelled = true
    }
  }, [selected])

  if (error) {
    return (
      <p data-testid="briefing-error" className="text-sm text-destructive">
        Failed to load briefings: {error}
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
                onClick={() => setSelected(file)}
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
