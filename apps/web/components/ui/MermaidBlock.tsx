"use client"

import { useEffect, useId, useState } from "react"

import { MermaidModal } from "@/components/ui/MermaidModal"

type RenderState =
  | { status: "loading" }
  | { status: "success"; svg: string }
  | { status: "error"; message: string }

// mermaid.initialize() only needs to run once per page load, not per mount.
// `securityLevel: "strict"` disables raw HTML/script content in diagram
// labels so the SVG we pass to dangerouslySetInnerHTML below can't carry
// injected markup even though the diagram source ultimately comes from
// user-authored markdown.
let mermaidInitialized = false

export function MermaidBlock({ code }: { code: string }) {
  const rawId = useId()
  const elementId = `mermaid-${rawId.replace(/:/g, "")}`
  const [state, setState] = useState<RenderState>({ status: "loading" })
  const [isModalOpen, setIsModalOpen] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function run() {
      try {
        const { default: mermaid } = await import("mermaid")
        if (!mermaidInitialized) {
          mermaid.initialize({ startOnLoad: false, securityLevel: "strict" })
          mermaidInitialized = true
        }
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

  return (
    <>
      {/* biome-ignore lint/security/noDangerouslySetInnerHtml: SVG string is generated locally by mermaid.render, not from untrusted user input rendered as HTML from the network. */}
      <div
        className="my-2 cursor-zoom-in"
        onClick={() => setIsModalOpen(true)}
        dangerouslySetInnerHTML={{ __html: state.svg }}
      />
      {isModalOpen && (
        <MermaidModal svg={state.svg} onClose={() => setIsModalOpen(false)} />
      )}
    </>
  )
}
