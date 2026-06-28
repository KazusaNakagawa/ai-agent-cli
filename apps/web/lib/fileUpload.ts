import type { FileAttachment } from "@/lib/types/attachment"

export async function uploadFile(file: File): Promise<FileAttachment> {
  const body = new FormData()
  body.append("file", file)

  const res = await fetch("/api/attachments/upload", { method: "POST", body })
  const json = (await res.json()) as {
    url?: string
    path?: string
    name?: string
    error?: string
  }

  if (!res.ok || !json.url || !json.path || !json.name) {
    throw new Error(json.error ?? "Upload failed, please try again")
  }

  return { url: json.url, path: json.path, name: json.name }
}
