"use client"
import type { Element, Nodes, Root } from "hast"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import { defaultSchema } from "rehype-sanitize"
import rehypeSanitize from "rehype-sanitize"
import remarkGfm from "remark-gfm"
import { visit } from "unist-util-visit"

import {
  BriefingFile,
  BriefingFileResponse,
  BriefingListResponse,
  BRIEFING_TYPE_LABELS,
} from "@/lib/briefing-types"
import { cn } from "@/lib/utils"

// ── TOC helpers ───────────────────────────────────────────────────────────────

interface TocEntry {
  id: string
  text: string
  level: number
}

// Slug used for heading ids. It only needs to be identical between extractToc
// and the rehype plugin (CSS.escape handles any leftover characters at query
// time), so we avoid \p{…} unicode escapes for broad target compatibility.
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[\s]+/g, "-")
    .replace(/["'`()[\]{}<>（）「」、。,.!?！？:：;；/\\|#*~]/g, "")
}

// Extract text from a hast node recursively
function hastText(node: Nodes): string {
  if (node.type === "text") return node.value
  if ("children" in node) return node.children.map(hastText).join("")
  return ""
}

// rehype plugin: attach id to h1/h2/h3 before sanitization
function rehypeHeadingIds() {
  return (tree: Root) => {
    const seen = new Map<string, number>()
    visit(tree, "element", (node: Element) => {
      if (!/^h[1-3]$/.test(node.tagName)) return
      const text = hastText(node)
      const base = slugify(text)
      const count = seen.get(base) ?? 0
      const id = count === 0 ? base : `${base}-${count}`
      seen.set(base, count + 1)
      node.properties = { ...node.properties, id }
    })
  }
}

// Allow id on heading elements so TOC scroll targets survive sanitization.
// clobberPrefix is cleared so heading ids match the slugs computed in extractToc
// (default prefixes them with "user-content-", breaking querySelector lookups).
const sanitizeSchema = {
  ...defaultSchema,
  clobberPrefix: "",
  attributes: {
    ...defaultSchema.attributes,
    h1: [...(defaultSchema.attributes?.h1 ?? []), "id"],
    h2: [...(defaultSchema.attributes?.h2 ?? []), "id"],
    h3: [...(defaultSchema.attributes?.h3 ?? []), "id"],
  },
}

function extractToc(markdown: string): TocEntry[] {
  const entries: TocEntry[] = []
  const seen = new Map<string, number>()
  for (const line of markdown.split("\n")) {
    const m = line.match(/^(#{1,3})\s+(.+)/)
    if (!m) continue
    const level = m[1].length
    const text = m[2].trim()
    const base = slugify(text)
    const count = seen.get(base) ?? 0
    const id = count === 0 ? base : `${base}-${count}`
    seen.set(base, count + 1)
    entries.push({ id, text, level })
  }
  return entries
}

// ── TOC sidebar ───────────────────────────────────────────────────────────────

interface TocProps {
  entries: TocEntry[]
  scrollContainer: React.RefObject<HTMLDivElement | null>
  activeId: string | null
  onClose: () => void
}

function Toc({ entries, scrollContainer, activeId, onClose }: TocProps) {
  if (entries.length === 0) return null

  const scrollTo = (id: string) => {
    const root = scrollContainer.current
    const el = root?.querySelector<HTMLElement>(`[id="${CSS.escape(id)}"]`)
    if (el) {
      // scrollIntoView walks every scrollable ancestor and brings the heading to
      // the top. scroll-margin-top (set in the className below) keeps it clear of
      // the sticky header.
      el.scrollIntoView({ behavior: "smooth", block: "start" })
    }
    onClose()
  }

  return (
    <nav
      data-testid="briefing-toc"
      className="absolute right-0 top-0 bottom-0 w-56 overflow-y-auto border-l bg-background/30 px-3 py-4 backdrop-blur-sm"
    >
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        目次
      </p>
      <ul className="space-y-0.5">
        {entries.map((entry) => (
          <li key={entry.id}>
            <button
              onClick={() => scrollTo(entry.id)}
              className={cn(
                "w-full rounded px-2 py-1 text-left text-xs transition-colors hover:bg-accent hover:text-accent-foreground",
                entry.level === 1 && "font-medium",
                entry.level === 2 && "pl-4 text-muted-foreground",
                entry.level === 3 && "pl-6 text-muted-foreground/70",
                activeId === entry.id && "bg-accent/60 text-accent-foreground",
              )}
            >
              {entry.text}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}

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
  const [tocVisible, setTocVisible] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)

  const toc = useMemo(() => (content ? extractToc(content) : []), [content])

  // Track which heading is in view
  useEffect(() => {
    if (!bodyRef.current || toc.length === 0 || typeof IntersectionObserver === "undefined") return
    const container = bodyRef.current
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.getAttribute("id"))
            break
          }
        }
      },
      { root: container, rootMargin: "0px 0px -80% 0px", threshold: 0 },
    )
    container.querySelectorAll("h1[id], h2[id], h3[id]").forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [toc, content])

  return (
    <div
      data-testid="briefing-panel"
      className={cn(
        "flex flex-col overflow-hidden bg-background transition-all",
        fullSize ? "rounded-lg border" : "border-l",
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
          {toc.length > 0 && (
            <button
              data-testid="panel-toc-btn"
              onClick={() => setTocVisible((v) => !v)}
              aria-label="Toggle table of contents"
              className={cn(
                "rounded p-1 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                tocVisible && "bg-accent text-accent-foreground",
              )}
            >
              目次
            </button>
          )}
          <button
            data-testid="panel-fullsize-btn"
            onClick={onToggleFullSize}
            aria-label={fullSize ? "Collapse" : "Full size"}
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            {fullSize ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M8 3v3a2 2 0 0 1-2 2H3" />
                <path d="M21 8h-3a2 2 0 0 1-2-2V3" />
                <path d="M3 16h3a2 2 0 0 1 2 2v3" />
                <path d="M16 21v-3a2 2 0 0 1 2-2h3" />
              </svg>
            ) : (
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

      {/* Panel body + TOC overlay */}
      <div className="relative flex-1 overflow-hidden">
        <div ref={bodyRef} className="h-full overflow-y-auto px-4 py-4 pr-6">
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
              className="prose prose-sm max-w-none dark:prose-invert prose-headings:scroll-mt-4 prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline dark:prose-a:text-blue-400"
            >
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHeadingIds, [rehypeSanitize, sanitizeSchema]]}
              >
                {content}
              </ReactMarkdown>
            </div>
          ) : null}
        </div>

        {/* TOC — appears on hover */}
        <div
          className={cn(
            "pointer-events-none absolute inset-y-0 right-0 transition-opacity duration-200",
            tocVisible ? "pointer-events-auto opacity-100" : "opacity-0",
          )}
        >
          <Toc entries={toc} scrollContainer={bodyRef} activeId={activeId} onClose={() => setTocVisible(false)} />
        </div>
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
    <div data-testid="briefing-dashboard" className="flex h-full">
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

      {/* Side panel */}
      {selected && (
        <div className={cn("overflow-hidden", fullSize ? "flex-1" : "flex-1")}>
          <BriefingPanel
            file={selected}
            content={content}
            loading={loadingContent}
            error={contentError}
            fullSize={fullSize}
            onToggleFullSize={() => setFullSize((v) => !v)}
            onClose={handleClose}
          />
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
