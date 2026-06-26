"use client"
import type { ImageAttachment } from "@/lib/types/image"

type Props = {
  image: ImageAttachment
  onRemove: () => void
}

export function ImageAttachmentPreview({ image, onRemove }: Props) {
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
        aria-label="Remove attached image"
        onClick={onRemove}
        className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] text-destructive-foreground"
      >
        ✕
      </button>
    </div>
  )
}
