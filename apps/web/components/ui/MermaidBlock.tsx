"use client"

import { useEffect, useId, useState } from "react"

type RenderState =
  | { status: "loading" }
  | { status: "success"; svg: string }
  | { status: "error"; message: string }

export function MermaidBlock({ code }: { code: string }) {
  const rawId = useId()
  const elementId = `mermaid-${rawId.replace(/:/g, "")}`
  const [state, setState] = useState<RenderState>({ status: "loading" })

  useEffect(() => {
    let cancelled = false

    async function run() {
      try {
        const { default: mermaid } = await import("mermaid")
        mermaid.initialize({ startOnLoad: false })
        const { svg } = await mermaid.render(elementId, code)
        if (!cancelled) {
          setState({ status: "success", svg })
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : String(err)
          setState({ status: "error", message })
        }
      }
    }

    void run()

    return () => {
      cancelled = true
    }
  }, [code, elementId])

  if (state.status === "loading") {
    return <div className="text-sm text-gray-500">Rendering mermaid diagram...</div>
  }

  if (state.status === "error") {
    return (
      <div className="my-2">
        <p className="text-sm text-red-600 dark:text-red-400">
          Mermaid render error: {state.message}
        </p>
        <details className="mt-1">
          <summary className="cursor-pointer text-sm text-gray-500">Show source</summary>
          <pre className="whitespace-pre-wrap text-xs">
            <code>{code}</code>
          </pre>
        </details>
      </div>
    )
  }

  // biome-ignore lint/security/noDangerouslySetInnerHtml: SVG string is generated locally by mermaid.render, not from untrusted user input rendered as HTML from the network.
  return <div className="my-2" dangerouslySetInnerHTML={{ __html: state.svg }} />
}
