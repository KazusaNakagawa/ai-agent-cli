import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ImageAttachment } from "@/lib/types/image"
import { uploadImage } from "@/lib/imageUpload"

function makeFile(name: string, type: string, size = 100): File {
  const buf = new Uint8Array(size)
  return new File([buf], name, { type })
}

describe("uploadImage", () => {
  beforeEach(() => { vi.stubGlobal("fetch", vi.fn()) })
  afterEach(() => { vi.restoreAllMocks() })

  it("returns ImageAttachment on success", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          url: "/api/images/2026-06-26/abc.png",
          path: "/abs/apps/python/input/images/2026-06-26/abc.png",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    )
    const file = makeFile("photo.png", "image/png")
    const result: ImageAttachment = await uploadImage(file)
    expect(result.url).toBe("/api/images/2026-06-26/abc.png")
    expect(result.path).toBe("/abs/apps/python/input/images/2026-06-26/abc.png")
  })

  it("throws with server error message on 400", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: "Image must be under 5 MB" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      })
    )
    await expect(uploadImage(makeFile("big.png", "image/png"))).rejects.toThrow(
      "Image must be under 5 MB"
    )
  })

  it("throws on network failure", async () => {
    vi.mocked(fetch).mockRejectedValue(new Error("Network error"))
    await expect(uploadImage(makeFile("photo.png", "image/png"))).rejects.toThrow(
      "Network error"
    )
  })
})
