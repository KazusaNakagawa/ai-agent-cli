"use client"
import { useRef, useState } from "react"
import type { ImageAttachment } from "@/lib/types/image"
import { uploadImages } from "@/lib/uploadImages"

type Props = {
  onAttach: (image: ImageAttachment) => void
  disabled?: boolean
}

export function ImageInsertButton({ onAttach, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    if (files.length === 0) return
    setError(null)
    setUploading(true)
    // Attached in selection order; one failed upload doesn't drop the rest.
    const { attachments, error } = await uploadImages(files)
    attachments.forEach((attachment) => onAttach(attachment))
    setError(error)
    setUploading(false)
    if (inputRef.current) inputRef.current.value = ""
  }

  return (
    <div className="flex flex-col gap-1">
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        multiple
        className="hidden"
        onChange={handleChange}
      />
      <button
        type="button"
        aria-label="Attach image"
        disabled={disabled || uploading}
        onClick={() => inputRef.current?.click()}
        className="flex h-8 w-8 items-center justify-center rounded-md border bg-background text-sm font-medium hover:bg-accent disabled:opacity-50"
      >
        {uploading ? "…" : "+"}
      </button>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
