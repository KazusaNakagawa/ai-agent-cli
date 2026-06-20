import { useEffect, useMemo, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"
import remarkGfm from "remark-gfm"

import { extractToc, rehypeHeadingIds, sanitizeSchema } from "@/lib/briefing-toc"
import { BriefingFile, BRIEFING_TYPE_LABELS } from "@/lib/briefing-types"
import { cn } from "@/lib/utils"

import { BriefingToc } from "./BriefingToc"
import { CloseIcon, CompressIcon, ExpandIcon } from "./icons"

const PROSE_CLASS =
  "prose prose-sm max-w-none dark:prose-invert prose-headings:scroll-mt-4 " +
  "prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline dark:prose-a:text-blue-400"

const HEADER_BTN =
  "rounded p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"

// Track the heading currently scrolled into view within `containerRef`.
function useActiveHeading(containerRef: React.RefObject<HTMLDivElement | null>, deps: unknown[]) {
  const [activeId, setActiveId] = useState<string | null>(null)
  useEffect(() => {
    const container = containerRef.current
    if (!container || typeof IntersectionObserver === "undefined") return
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return activeId
}

interface BriefingPanelProps {
  file: BriefingFile
  content: string | null
  loading: boolean
  error: string | null
  fullSize: boolean
  onToggleFullSize: () => void
  onClose: () => void
}

export function BriefingPanel({
  file,
  content,
  loading,
  error,
  fullSize,
  onToggleFullSize,
  onClose,
}: BriefingPanelProps) {
  const [tocVisible, setTocVisible] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)

  const toc = useMemo(() => (content ? extractToc(content) : []), [content])
  const activeId = useActiveHeading(bodyRef, [toc, content])

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
            className={HEADER_BTN}
          >
            {fullSize ? <CompressIcon /> : <ExpandIcon />}
          </button>
          <button
            data-testid="panel-close-btn"
            onClick={onClose}
            aria-label="Close panel"
            className={HEADER_BTN}
          >
            <CloseIcon />
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
            <div data-testid="briefing-content" className={PROSE_CLASS}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHeadingIds, [rehypeSanitize, sanitizeSchema]]}
              >
                {content}
              </ReactMarkdown>
            </div>
          ) : null}
        </div>

        {/* TOC — toggled from the header */}
        <div
          className={cn(
            "pointer-events-none absolute inset-y-0 right-0 transition-opacity duration-200",
            tocVisible ? "pointer-events-auto opacity-100" : "opacity-0",
          )}
        >
          <BriefingToc
            entries={toc}
            scrollContainer={bodyRef}
            activeId={activeId}
            onClose={() => setTocVisible(false)}
          />
        </div>
      </div>
    </div>
  )
}
