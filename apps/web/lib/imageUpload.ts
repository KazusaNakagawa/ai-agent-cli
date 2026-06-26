export async function uploadImage(file: File): Promise<string> {
  const body = new FormData()
  body.append("file", file)

  const res = await fetch("/api/images/upload", { method: "POST", body })
  const json = (await res.json()) as { url?: string; error?: string }

  if (!res.ok || !json.url) {
    throw new Error(json.error ?? "Upload failed, please try again")
  }

  return `![image](${json.url})`
}
