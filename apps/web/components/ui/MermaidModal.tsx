"use client"

import { useEffect } from "react"
import { TransformComponent, TransformWrapper, useControls } from "react-zoom-pan-pinch"

function ZoomControls() {
  const { zoomIn, zoomOut, resetTransform } = useControls()

  return (
    <div className="absolute bottom-4 right-4 z-10 flex flex-col gap-2">
      <button
        type="button"
        aria-label="Zoom in"
        className="rounded bg-gray-800 px-3 py-2 text-white"
        onClick={() => zoomIn()}
      >
        +
      </button>
      <button
        type="button"
        aria-label="Reset zoom"
        className="rounded bg-gray-800 px-3 py-2 text-white"
        onClick={() => resetTransform()}
      >
        ⟳
      </button>
      <button
        type="button"
        aria-label="Zoom out"
        className="rounded bg-gray-800 px-3 py-2 text-white"
        onClick={() => zoomOut()}
      >
        −
      </button>
    </div>
  )
}

export function MermaidModal({ svg, onClose }: { svg: string; onClose: () => void }) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handleKeyDown)

    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [onClose])

  return (
    <div
      data-testid="mermaid-modal-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
      onClick={onClose}
    >
      <button
        type="button"
        aria-label="Close"
        className="absolute right-4 top-4 text-2xl text-white"
        onClick={(e) => {
          e.stopPropagation()
          onClose()
        }}
      >
        ×
      </button>
      <div
        className="relative h-[80vh] w-[80vw] bg-gray-950"
        onClick={(e) => e.stopPropagation()}
      >
        <TransformWrapper wheel={{ disabled: true }}>
          <ZoomControls />
          <TransformComponent wrapperStyle={{ width: "100%", height: "100%" }}>
            {/* biome-ignore lint/security/noDangerouslySetInnerHtml: SVG string is generated locally by mermaid.render, not from untrusted user input rendered as HTML from the network. */}
            <div dangerouslySetInnerHTML={{ __html: svg }} />
          </TransformComponent>
        </TransformWrapper>
      </div>
    </div>
  )
}
