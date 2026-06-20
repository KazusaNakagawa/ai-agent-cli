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

// ── Panel view ────────────────────────────────────────────────────────────────

interface PanelProps {
  file: BriefingFile
  content: string | null
  loading: boolean
  error: string | null
  fullSize: boolean
  onToggleFullSize: () => void
  onClose: () => void
}

function BriefingPanel({
  file,
  content,
  loading,
  error,
  fullSize,
  onToggleFullSize,
  onClose,
}: PanelProps) {
  return (
    <div
      data-testid="briefing-panel"
      className={cn(
        "flex flex-col overflow-hidden border-l bg-background transition-all",
        "relative",
      )}
    >
      {/* Panel header */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex gap-3 text-xs text-muted-foreground">
          <span data-testid="panel-type">{BRIEFING_TYPE_LABELS[file.type]}</span>
          <span data-testid="panel-date">{file.date}</span>
          <span data-testid="panel-size">{(file.size / 1024).toFixed(1)} KB</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            data-testid="panel-fullsize-btn"
            onClick={onToggleFullSize}
            aria-label={fullSize ? "Collapse" : "Full size"}
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            {fullSize ? (
              // Compress icon
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M8 3v3a2 2 0 0 1-2 2H3" />
                <path d="M21 8h-3a2 2 0 0 1-2-2V3" />
                <path d="M3 16h3a2 2 0 0 1 2 2v3" />
                <path d="M16 21v-3a2 2 0 0 1 2-2h3" />
              </svg>
            ) : (
              // Expand icon
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M15 3h6v6" />
                <path d="M9 21H3v-6" />
                <path d="M21 3l-7 7" />
                <path d="M3 21l7-7" />
              </svg>
            )}
          </button>
          <button
            data-testid="panel-close-btn"
            onClick={onClose}
            aria-label="Close panel"
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      {/* Panel title */}
      <div className="border-b px-4 py-3">
        <h2 className="text-sm font-semibold" data-testid="panel-title">{file.name}</h2>
      </div>

      {/* Panel body */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {loading ? (
          <p data-testid="briefing-content-loading" className="text-sm text-muted-foreground">
            Loading…
          </p>
        ) : error !== null ? (
          <p data-testid="briefing-content-error" className="text-sm text-destructive">
            Failed to load content: {error}
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
      </div>
    </div>
  )
}

// ── Main dashboard ─────────────────────────────────────────────────────────────

export function BriefingDashboard() {
  const [files, setFiles] = useState<BriefingFile[] | null>(null)
  const [selected, setSelected] = useState<BriefingFile | null>(null)
  const [content, setContent] = useState<string | null>(null)
  const [loadingContent, setLoadingContent] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [contentError, setContentError] = useState<string | null>(null)
  const [fullSize, setFullSize] = useState(false)

  const contentCache = useRef(new Map<string, string>())
  const latestFile = useRef<string | null>(null)

  const fetchContent = useCallback((file: BriefingFile) => {
    latestFile.current = file.name
    const cached = contentCache.current.get(file.name)
    if (cached !== undefined) {
      setSelected(file)
      setContent(cached)
      setLoadingContent(false)
      return
    }
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
      })
      .catch((e) => {
        if (!cancelled) setListError(String(e))
      })
    return () => {
      cancelled = true
    }
  }, [])

  const handleClose = useCallback(() => {
    setSelected(null)
    setContent(null)
    setContentError(null)
    setFullSize(false)
  }, [])

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
    <div data-testid="briefing-dashboard" className="relative flex h-full">
      {/* Records list */}
      <div
        className={cn(
          "flex-shrink-0 overflow-y-auto border-r transition-all",
          selected && !fullSize ? "w-72" : "flex-1",
          fullSize && "hidden",
        )}
      >
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Date</th>
              <th className="w-8 px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {files.map((file) => (
              <BriefingRow
                key={file.name}
                file={file}
                selected={selected?.name === file.name}
                onOpen={fetchContent}
                onHover={prefetch}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Side panel — normal mode */}
      {selected && !fullSize && (
        <div className="flex-1 overflow-hidden">
          <BriefingPanel
            file={selected}
            content={content}
            loading={loadingContent}
            error={contentError}
            fullSize={false}
            onToggleFullSize={() => setFullSize(true)}
            onClose={handleClose}
          />
        </div>
      )}

      {/* Full-size overlay within main content area (sidebar stays visible) */}
      {selected && fullSize && (
        <div className="absolute inset-0 grid grid-cols-[1fr_8fr_1fr] bg-background">
          <div />
          <BriefingPanel
            file={selected}
            content={content}
            loading={loadingContent}
            error={contentError}
            fullSize={true}
            onToggleFullSize={() => setFullSize(false)}
            onClose={handleClose}
          />
          <div />
        </div>
      )}
    </div>
  )
}

// ── Row with hover open icon ───────────────────────────────────────────────────

interface RowProps {
  file: BriefingFile
  selected: boolean
  onOpen: (file: BriefingFile) => void
  onHover: (file: BriefingFile) => void
}

function BriefingRow({ file, selected, onOpen, onHover }: RowProps) {
  const [hovered, setHovered] = useState(false)

  return (
    <tr
      data-testid={`briefing-row-${file.name}`}
      tabIndex={0}
      onMouseEnter={() => {
        setHovered(true)
        onHover(file)
      }}
      onMouseLeave={() => setHovered(false)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onOpen(file)
        }
      }}
      className={cn(
        "group border-b text-xs transition-colors last:border-0",
        selected ? "bg-accent font-medium text-accent-foreground" : "hover:bg-accent/50",
      )}
    >
      <td className="max-w-[160px] truncate px-3 py-2" title={file.name}>
        {file.name}
      </td>
      <td className="px-3 py-2">{BRIEFING_TYPE_LABELS[file.type]}</td>
      <td className="px-3 py-2 tabular-nums">{file.date}</td>
      <td className="px-2 py-2">
        <button
          data-testid={`briefing-open-${file.name}`}
          onClick={() => onOpen(file)}
          aria-label={`Open ${file.name}`}
          className={cn(
            "rounded p-0.5 text-muted-foreground transition-opacity hover:bg-accent hover:text-accent-foreground",
            hovered ? "opacity-100" : "opacity-0",
          )}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </button>
      </td>
    </tr>
  )
}
