import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { FileAttachment } from "@/lib/types/attachment"
import { uploadFile } from "@/lib/fileUpload"

function makeFile(name: string, type: string, size = 100): File {
  const buf = new Uint8Array(size)
  return new File([buf], name, { type })
}

describe("uploadFile", () => {
  beforeEach(() => { vi.stubGlobal("fetch", vi.fn()) })
  afterEach(() => { vi.restoreAllMocks() })

  it("returns FileAttachment on success", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          url: "/api/attachments/2026-06-28/abc.csv",
          path: "/abs/apps/python/input/attachments/2026-06-28/abc.csv",
          name: "report.csv",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    )
    const result: FileAttachment = await uploadFile(makeFile("report.csv", "text/csv"))
    expect(result.url).toBe("/api/attachments/2026-06-28/abc.csv")
    expect(result.name).toBe("report.csv")
  })

  it("throws with server error message on 400", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: "File must be under 10 MB" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      })
    )
    await expect(uploadFile(makeFile("big.pdf", "application/pdf"))).rejects.toThrow(
      "File must be under 10 MB"
    )
  })

  it("throws on network failure", async () => {
    vi.mocked(fetch).mockRejectedValue(new Error("Network error"))
    await expect(uploadFile(makeFile("a.txt", "text/plain"))).rejects.toThrow(
      "Network error"
    )
  })
})
