"use client"
import { useCallback, useRef, useState } from "react"
import type { RefObject } from "react"
import { useImageDrop } from "@/lib/hooks/useImageDrop"
import { useImagePaste } from "@/lib/hooks/useImagePaste"
import { MAX_IMAGES_PER_MESSAGE, type ImageAttachment } from "@/lib/types/image"

/**
 * The images attached to one message box, from any route: drop or paste onto
 * `ref`, or `attach` from a picker. Enforces MAX_IMAGES_PER_MESSAGE and keeps
 * the notice to show beside the box.
 */
export function useImageAttachments(ref: RefObject<HTMLTextAreaElement>) {
  const [images, setImagesState] = useState<ImageAttachment[]>([])
  // Mirrors the state so overlapping uploads append to the latest list and
  // the limit check sees images attached earlier in the same tick.
  const imagesRef = useRef<ImageAttachment[]>([])
  const [error, setError] = useState<string | null>(null)

  const setImages = useCallback((next: ImageAttachment[]) => {
    imagesRef.current = next
    setImagesState(next)
  }, [])

  const attach = useCallback(
    (image: ImageAttachment) => {
      if (imagesRef.current.length >= MAX_IMAGES_PER_MESSAGE) {
        setError(`Up to ${MAX_IMAGES_PER_MESSAGE} images per message`)
        return
      }
      setImages([...imagesRef.current, image])
    },
    [setImages]
  )

  const remove = useCallback(
    (index: number) => setImages(imagesRef.current.filter((_, i) => i !== index)),
    [setImages]
  )

  /** Returns the attached paths and clears the box, for a send. */
  const take = useCallback(() => {
    const paths = imagesRef.current.map((image) => image.path)
    setImages([])
    setError(null)
    return paths
  }, [setImages])

  const { isDragging } = useImageDrop(ref, attach)
  const { pasting } = useImagePaste(ref, attach, setError)

  return { images, attach, remove, take, error, isDragging, pasting }
}
