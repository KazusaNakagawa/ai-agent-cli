import type React from "react"
import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"
import remarkGfm from "remark-gfm"

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

function makeMarkdownComponents(onLinkClick?: LinkHandler) {
  return {
    a: ({ children, href, ...props }: React.ComponentPropsWithoutRef<"a">) => (
      <a
        {...props}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => {
          if (href !== undefined && (onLinkClick?.(href) ?? false)) {
            e.preventDefault()
          }
        }}
      >
        {children}
      </a>
    ),
  }
}

export function MarkdownView({
  content,
  onLinkClick,
}: {
  content: string
  onLinkClick?: LinkHandler
}) {
  return (
    <div className={PROSE_CLASS} data-testid="markdown-view">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
        components={makeMarkdownComponents(onLinkClick)}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
