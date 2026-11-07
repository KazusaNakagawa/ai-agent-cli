"use client"
import type { ImageAttachment } from "@/lib/types/image"
import { ImageInsertButton } from "@/components/ui/ImageInsertButton"
import { ImageAttachmentPreview } from "@/components/ui/ImageAttachmentPreview"
import { AttachMenu } from "@/components/ui/AttachMenu"

type Props = {
  attachedImages: ImageAttachment[]
  onAttach: (image: ImageAttachment) => void
  /** Called with the position of the image to drop. */
  onRemove: (index: number) => void
  disabled?: boolean
  isDragging?: boolean
  // When provided, the "+" becomes a menu (image + generic file). The callback
  // receives the Markdown link to splice in at the caret.
  onInsertFile?: (markdown: string) => void
  /** Forwarded to the picker: whether one of its uploads is in flight. */
  onUploadingChange?: (uploading: boolean) => void
}

export function ImageAttachArea({
  attachedImages,
  onAttach,
  onRemove,
  disabled,
  isDragging,
  onInsertFile,
  onUploadingChange,
}: Props) {
  return (
    <div
      className={`flex items-center gap-2 ${isDragging ? "ring-2 ring-primary rounded-md" : ""}`}
    >
      {onInsertFile ? (
        <AttachMenu
          onAttachImage={onAttach}
          onInsertFile={onInsertFile}
          disabled={disabled}
          onUploadingChange={onUploadingChange}
        />
      ) : (
        <ImageInsertButton
          onAttach={onAttach}
          disabled={disabled}
          onUploadingChange={onUploadingChange}
        />
      )}
      {attachedImages.map((image, i) => (
        <ImageAttachmentPreview
          key={image.path}
          image={image}
          index={attachedImages.length > 1 ? i : undefined}
          onRemove={() => onRemove(i)}
        />
      ))}
    </div>
  )
}
