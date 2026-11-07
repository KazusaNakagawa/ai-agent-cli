"use client"
import { useEffect, useRef, useState } from "react"
import type { RefObject } from "react"
import type { ImageAttachment } from "@/lib/types/image"
import { uploadImages } from "@/lib/uploadImages"

export function useImageDrop(
  ref: RefObject<HTMLTextAreaElement>,
  onAttach: (image: ImageAttachment) => void
): { isDragging: boolean; dropping: boolean } {
  const [isDragging, setIsDragging] = useState(false)
  // Drops can overlap; `dropping` stays on until the last upload settles.
  const [dropping, setDropping] = useState(false)
  const pendingRef = useRef(0)
  const onAttachRef = useRef(onAttach)
  onAttachRef.current = onAttach

  useEffect(() => {
    // Handlers live on `document`, not on the textarea, so they work even when
    // the textarea mounts later (e.g. the Journal brainstorm box only renders
    // once an entry is selected — element-scoped listeners would never attach).
    // The drop is claimed only when the event target is inside `ref.current`;
    // everywhere else we still preventDefault to stop the browser from opening
    // the dropped file in a new tab.
    function isFileDrag(e: DragEvent): boolean {
      return e.dataTransfer?.types.includes("Files") ?? false
    }

    function insideTarget(e: DragEvent): boolean {
      const el = ref.current
      return !!el && e.target instanceof Node && el.contains(e.target)
    }

    function onDragOver(e: DragEvent) {
      if (!isFileDrag(e)) return
      // Always block the browser default so a near-miss drop never navigates.
      e.preventDefault()
      setIsDragging(insideTarget(e))
    }

    function onDragLeave(e: DragEvent) {
      // relatedTarget is null when the cursor leaves the window entirely.
      if (!e.relatedTarget) setIsDragging(false)
    }

    async function onDrop(e: DragEvent) {
      if (!isFileDrag(e)) return
      e.preventDefault()
      setIsDragging(false)
      if (!insideTarget(e)) return
      const files = Array.from(e.dataTransfer?.files ?? []).filter((f) =>
        f.type.startsWith("image/")
      )
      if (files.length === 0) return
      pendingRef.current++
      setDropping(true)
      // Attached in drop order. Failures stay silent — there is no persistent
      // UI anchor for drop errors.
      const { attachments } = await uploadImages(files)
      attachments.forEach((attachment) => onAttachRef.current(attachment))
      if (--pendingRef.current === 0) setDropping(false)
    }

    document.addEventListener("dragover", onDragOver)
    document.addEventListener("dragleave", onDragLeave)
    document.addEventListener("drop", onDrop)
    return () => {
      document.removeEventListener("dragover", onDragOver)
      document.removeEventListener("dragleave", onDragLeave)
      document.removeEventListener("drop", onDrop)
    }
  }, [ref])

  return { isDragging, dropping }
}
