"use client"
import type { RefObject } from "react"
import type { ImageAttachment } from "@/lib/types/image"
import { ImageInsertButton } from "@/components/ui/ImageInsertButton"
import { ImageAttachmentPreview } from "@/components/ui/ImageAttachmentPreview"

type Props = {
  textareaRef: RefObject<HTMLTextAreaElement>
  attachedImage: ImageAttachment | null
  onAttach: (image: ImageAttachment) => void
  onRemove: () => void
  disabled?: boolean
  isDragging?: boolean
}

export function ImageAttachArea({
  attachedImage,
  onAttach,
  onRemove,
  disabled,
  isDragging,
}: Props) {
  return (
    <div
      className={`flex items-center gap-2 ${isDragging ? "ring-2 ring-primary rounded-md" : ""}`}
    >
      <ImageInsertButton onAttach={onAttach} disabled={disabled} />
      {attachedImage && (
        <ImageAttachmentPreview image={attachedImage} onRemove={onRemove} />
      )}
    </div>
  )
}
