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
    const el = ref.current
    if (!el) return

    function onDragEnter(e: DragEvent) {
      e.preventDefault()
      e.stopPropagation()
    }

    function onDragOver(e: DragEvent) {
      if (!e.dataTransfer?.types.includes("Files")) return
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(true)
    }

    function onDragLeave() {
      setIsDragging(false)
    }

    async function onDrop(e: DragEvent) {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)
      const file = e.dataTransfer?.files[0]
      if (!file || !file.type.startsWith("image/")) return
      try {
        const attachment = await uploadImage(file)
        onAttachRef.current(attachment)
      } catch {
        // Silent — no persistent UI anchor for drop errors
      }
    }

    el.addEventListener("dragenter", onDragEnter)
    el.addEventListener("dragover", onDragOver)
    el.addEventListener("dragleave", onDragLeave)
    el.addEventListener("drop", onDrop)
    return () => {
      el.removeEventListener("dragenter", onDragEnter)
      el.removeEventListener("dragover", onDragOver)
      el.removeEventListener("dragleave", onDragLeave)
      el.removeEventListener("drop", onDrop)
    }
  }, [ref])

  return { isDragging }
}
