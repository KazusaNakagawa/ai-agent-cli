"use client"
import { X } from "lucide-react"
import type { ImageAttachment } from "@/lib/types/image"

type Props = {
  image: ImageAttachment
  onRemove: () => void
  /** Position in a list of attachments, numbered in the remove button's label. */
  index?: number
}

export function ImageAttachmentPreview({ image, onRemove, index }: Props) {
  return (
    <div className="relative inline-block">
      <img
        src={image.url}
        alt="Attached image"
        aria-label="Attached image"
        className="h-16 w-16 rounded-md border object-cover"
      />
      <button
        type="button"
        aria-label={
          index === undefined ? "Remove attached image" : `Remove attached image ${index + 1}`
        }
        onClick={onRemove}
        className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] text-destructive-foreground"
      >
        <X aria-hidden className="h-3 w-3" />
      </button>
    </div>
  )
}
