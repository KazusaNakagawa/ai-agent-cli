"use client"
import { useEffect, useRef, useState } from "react"
import type { RefObject } from "react"
import type { ImageAttachment } from "@/lib/types/image"
import { uploadImage } from "@/lib/imageUpload"

/**
 * Attaches the images pasted into `ref`, uploading them the same way a drop
 * does. Every image in a paste is attached, in clipboard order. The paste is
 * never default-prevented, so any text on the clipboard still lands in the
 * field.
 */
export function useImagePaste(
  ref: RefObject<HTMLTextAreaElement>,
  onAttach: (image: ImageAttachment) => void,
  onError: (message: string | null) => void
): { pasting: boolean } {
  const [pasting, setPasting] = useState(false)
  const onAttachRef = useRef(onAttach)
  onAttachRef.current = onAttach
  const onErrorRef = useRef(onError)
  onErrorRef.current = onError
  // Pastes can overlap; `pasting` stays on until the last one settles.
  const pendingRef = useRef(0)

  useEffect(() => {
    // On `document` for the same reason as useImageDrop: the textarea may
    // mount after this effect runs.
    async function onPaste(e: ClipboardEvent) {
      const el = ref.current
      if (!el || !(e.target instanceof Node) || !el.contains(e.target)) return
      const files = Array.from(e.clipboardData?.files ?? []).filter((f) =>
        f.type.startsWith("image/")
      )
      if (files.length === 0) return

      pendingRef.current++
      setPasting(true)
      onErrorRef.current(null)
      const results = await Promise.allSettled(files.map(uploadImage))
      let error: string | null = null
      for (const result of results) {
        if (result.status === "fulfilled") {
          onAttachRef.current(result.value)
        } else if (error === null) {
          error =
            result.reason instanceof Error
              ? result.reason.message
              : "Upload failed, please try again"
        }
      }
      if (error !== null) onErrorRef.current(error)
      if (--pendingRef.current === 0) setPasting(false)
    }

    document.addEventListener("paste", onPaste)
    return () => document.removeEventListener("paste", onPaste)
  }, [ref])

  return { pasting }
}
