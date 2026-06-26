import type { ImageAttachment } from "@/lib/types/image"

export async function uploadImage(file: File): Promise<ImageAttachment> {
  const body = new FormData()
  body.append("file", file)

  const res = await fetch("/api/images/upload", { method: "POST", body })
  const json = (await res.json()) as { url?: string; path?: string; error?: string }

  if (!res.ok || !json.url || !json.path) {
    throw new Error(json.error ?? "Upload failed, please try again")
  }

  return { url: json.url, path: json.path }
}
