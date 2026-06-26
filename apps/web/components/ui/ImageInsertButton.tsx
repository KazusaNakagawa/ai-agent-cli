"use client"
import { useRef, useState } from "react"
import { uploadImage } from "@/lib/imageUpload"

type Props = {
  onInsert: (snippet: string) => void
  disabled?: boolean
}

export function ImageInsertButton({ onInsert, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setError(null)
    setUploading(true)
    try {
      const snippet = await uploadImage(file)
      onInsert(snippet)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed, please try again")
    } finally {
      setUploading(false)
      // Reset so the same file can be re-selected
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        className="hidden"
        onChange={handleChange}
      />
      <button
        type="button"
        aria-label="Insert image"
        disabled={disabled || uploading}
        onClick={() => inputRef.current?.click()}
        className="flex h-8 w-8 items-center justify-center rounded-md border bg-background text-sm font-medium hover:bg-accent disabled:opacity-50"
      >
        {uploading ? "…" : "+"}
      </button>
      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}
    </div>
  )
}
