"use client"
import { useEffect, useRef, useState } from "react"
import { uploadImage } from "@/lib/imageUpload"
import { uploadFile } from "@/lib/fileUpload"
import type { ImageAttachment } from "@/lib/types/image"

type Props = {
  onAttachImage: (image: ImageAttachment) => void
  // Receives the Markdown link to splice in at the caret, e.g. "[report.csv](/api/attachments/…)".
  onInsertFile: (markdown: string) => void
  disabled?: boolean
}

/**
 * "+" button that opens a small menu offering "Insert image" (Claude Vision
 * flow) or "Attach file" (generic file → Markdown link inserted at the caret).
 * Images and files are routed to their own upload endpoints.
 */
export function AttachMenu({ onAttachImage, onInsertFile, disabled }: Props) {
  const imageInputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Close the menu on outside click or Escape.
  useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", onDocClick)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDocClick)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  async function handleImageChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setError(null)
    setBusy(true)
    try {
      onAttachImage(await uploadImage(file))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed, please try again")
    } finally {
      setBusy(false)
      if (imageInputRef.current) imageInputRef.current.value = ""
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setError(null)
    setBusy(true)
    try {
      const attachment = await uploadFile(file)
      onInsertFile(`[${attachment.name}](${attachment.url})`)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed, please try again")
    } finally {
      setBusy(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  return (
    <div ref={rootRef} className="relative flex flex-col gap-1">
      <input
        ref={imageInputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        className="hidden"
        onChange={handleImageChange}
      />
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.csv,.txt,.md"
        className="hidden"
        onChange={handleFileChange}
      />
      <button
        type="button"
        aria-label="Attach"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled || busy}
        onClick={() => setOpen((v) => !v)}
        className="flex h-8 w-8 items-center justify-center rounded-md border bg-background text-sm font-medium hover:bg-accent disabled:opacity-50"
      >
        {busy ? "…" : "+"}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 z-10 mb-1 min-w-[10rem] overflow-hidden rounded-md border bg-popover py-1 text-sm shadow-md"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              imageInputRef.current?.click()
            }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-accent"
          >
            🖼 Insert image
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              fileInputRef.current?.click()
            }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-accent"
          >
            📎 Attach file
          </button>
        </div>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
