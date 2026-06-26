"use client"
import { useEffect, useRef, useState } from "react"
import type { RefObject } from "react"
import type { ImageAttachment } from "@/lib/types/image"
import { uploadImage } from "@/lib/imageUpload"

export function useImageDrop(
  ref: RefObject<HTMLTextAreaElement>,
  onAttach: (image: ImageAttachment) => void
): { isDragging: boolean } {
  const [isDragging, setIsDragging] = useState(false)
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
      const file = e.dataTransfer?.files[0]
      if (!file || !file.type.startsWith("image/")) return
      try {
        const attachment = await uploadImage(file)
        onAttachRef.current(attachment)
      } catch {
        // Silent — no persistent UI anchor for drop errors
      }
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

  return { isDragging }
}
