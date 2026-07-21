import type React from "react"
import { useMemo } from "react"
import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"
import remarkGfm from "remark-gfm"

import { MermaidBlock } from "@/components/ui/MermaidBlock"
import { sanitizeSchema } from "@/lib/briefing-toc"

// Shared markdown renderer. Same plugin stack (GFM + sanitize) and prose styling
// used by the Briefing panel, extracted so other screens (Workspace preview)
// render markdown identically.
const PROSE_CLASS =
  "prose prose-sm max-w-none dark:prose-invert " +
  "prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline dark:prose-a:text-blue-400"

// `onLinkClick` lets a caller (e.g. Workspace) intercept a link's href before
// the browser navigates it. Returning true means the caller handled it (e.g.
// switched to another open file) and default navigation is suppressed;
// returning false (or omitting the prop) keeps the normal target=_blank open.
type LinkHandler = (href: string) => boolean

// react-markdown always passes fenced code block content as a single string
// or an array of strings (one per line/text node), never other React nodes.
function extractText(children: string | string[]): string {
  if (typeof children === "string") return children
  return children.map(extractText).join("")
}

function makeMarkdownComponents(onLinkClick?: LinkHandler) {
  return {
    a: ({ children, href, ...props }: React.ComponentPropsWithoutRef<"a">) => (
      <a
        {...props}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => {
          // Let modified clicks (middle-click, cmd/ctrl/shift-click) through
          // untouched so users can still open the link in a new tab/window.
          if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
            return
          }
          if (href !== undefined && (onLinkClick?.(href) ?? false)) {
            e.preventDefault()
          }
        }}
      >
        {children}
      </a>
    ),
    code: ({ className, children, ...props }: React.ComponentPropsWithoutRef<"code">) => {
      const isMermaid = className?.split(/\s+/).includes("language-mermaid")
      if (isMermaid) {
        return (
          <MermaidBlock
            code={extractText(children as string | string[]).replace(/\n$/, "")}
          />
        )
      }
      return (
        <code className={className} {...props}>
          {children}
        </code>
      )
    },
  }
}

export function MarkdownView({
  content,
  onLinkClick,
}: {
  content: string
  onLinkClick?: LinkHandler
}) {
  const components = useMemo(
    () => makeMarkdownComponents(onLinkClick),
    [onLinkClick],
  )
  return (
    <div className={PROSE_CLASS} data-testid="markdown-view">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
