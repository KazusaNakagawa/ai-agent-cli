import type { ImageAttachment } from "@/lib/types/image"
import { uploadImage } from "@/lib/imageUpload"

/**
 * Uploads several images in parallel. Successful uploads come back in input
 * order; a failure doesn't stop the rest, and the first failure's message is
 * returned for the caller to show.
 */
export async function uploadImages(
  files: File[]
): Promise<{ attachments: ImageAttachment[]; error: string | null }> {
  const results = await Promise.allSettled(files.map(uploadImage))
  const attachments: ImageAttachment[] = []
  let error: string | null = null
  for (const result of results) {
    if (result.status === "fulfilled") {
      attachments.push(result.value)
    } else if (error === null) {
      error =
        result.reason instanceof Error
          ? result.reason.message
          : "Upload failed, please try again"
    }
  }
  return { attachments, error }
}
