"use client"
import { useEffect, useRef, useState } from "react"
import type { RefObject } from "react"
import { uploadImage } from "@/lib/imageUpload"

export function useImageDrop(
  ref: RefObject<HTMLTextAreaElement>,
  onInsert: (snippet: string) => void
): { isDragging: boolean } {
  const [isDragging, setIsDragging] = useState(false)
  // Keep a stable ref to avoid stale closures over onInsert
  const onInsertRef = useRef(onInsert)
  onInsertRef.current = onInsert

  useEffect(() => {
    const el = ref.current
    if (!el) return

    function onDragOver(e: DragEvent) {
      if (!e.dataTransfer?.types.includes("Files")) return
      e.preventDefault()
      setIsDragging(true)
    }

    function onDragLeave() {
      setIsDragging(false)
    }

    async function onDrop(e: DragEvent) {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer?.files[0]
      if (!file || !file.type.startsWith("image/")) return
      try {
        const snippet = await uploadImage(file)
        onInsertRef.current(snippet)
      } catch {
        // Silent drop failure — no UI anchor to show an error
      }
    }

    el.addEventListener("dragover", onDragOver)
    el.addEventListener("dragleave", onDragLeave)
    el.addEventListener("drop", onDrop)
    return () => {
      el.removeEventListener("dragover", onDragOver)
      el.removeEventListener("dragleave", onDragLeave)
      el.removeEventListener("drop", onDrop)
    }
  }, [ref])

  return { isDragging }
}
