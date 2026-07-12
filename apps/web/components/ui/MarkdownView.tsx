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

const MARKDOWN_COMPONENTS = {
  a: ({ children, ...props }: React.ComponentPropsWithoutRef<"a">) => (
    <a {...props} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
}

export function MarkdownView({ content }: { content: string }) {
  return (
    <div className={PROSE_CLASS} data-testid="markdown-view">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
        components={MARKDOWN_COMPONENTS}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
