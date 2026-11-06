"use client"
import { useEffect, useRef, useState } from "react"
import type { RefObject } from "react"
import type { ImageAttachment } from "@/lib/types/image"
import { uploadImage } from "@/lib/imageUpload"

/**
 * Attaches an image pasted into `ref`, uploading it the same way a drop does.
 * The paste is never default-prevented, so any text on the clipboard still
 * lands in the field. Only the first image is taken because a message carries
 * one attachment.
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
  // Newest paste wins, so a slow earlier upload can't overwrite a later one.
  const latestRef = useRef(0)

  useEffect(() => {
    // On `document` for the same reason as useImageDrop: the textarea may
    // mount after this effect runs.
    async function onPaste(e: ClipboardEvent) {
      const el = ref.current
      if (!el || !(e.target instanceof Node) || !el.contains(e.target)) return
      const file = Array.from(e.clipboardData?.files ?? []).find((f) =>
        f.type.startsWith("image/")
      )
      if (!file) return

      const id = ++latestRef.current
      setPasting(true)
      onErrorRef.current(null)
      try {
        const attachment = await uploadImage(file)
        if (id === latestRef.current) onAttachRef.current(attachment)
      } catch (err) {
        if (id === latestRef.current) {
          onErrorRef.current(
            err instanceof Error ? err.message : "Upload failed, please try again"
          )
        }
      } finally {
        if (id === latestRef.current) setPasting(false)
      }
    }

    document.addEventListener("paste", onPaste)
    return () => document.removeEventListener("paste", onPaste)
  }, [ref])

  return { pasting }
}
