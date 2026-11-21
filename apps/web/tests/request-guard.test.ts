import { describe, expect, it } from "vitest"

import { rejectForeignRequest } from "@/lib/request-guard"

function req(headers: Record<string, string>): Request {
  return new Request("http://localhost:3000/api/x", { headers })
}

describe("rejectForeignRequest", () => {
  it.each(["localhost:3000", "127.0.0.1:3000", "[::1]:3000", "localhost"])(
    "allows loopback Host %s with no Origin (success)",
    (host) => {
      expect(rejectForeignRequest(req({ host }))).toBeNull()
    },
  )

  it("allows a same-origin Origin (success)", () => {
    const res = rejectForeignRequest(
      req({ host: "localhost:3000", origin: "http://localhost:3000" }),
    )
    expect(res).toBeNull()
  })

  it.each(["evil.example.com", "evil.example.com:3000", "192.168.1.5:3000", "localhost.evil.com"])(
    "rejects non-loopback Host %s with 403 (DNS rebinding)",
    async (host) => {
      const res = rejectForeignRequest(req({ host }))
      expect(res?.status).toBe(403)
    },
  )

  it("rejects a missing Host header (boundary)", () => {
    expect(rejectForeignRequest(req({}))?.status).toBe(403)
  })

  it("rejects a cross-origin Origin with 403 (CSRF)", () => {
    const res = rejectForeignRequest(
      req({ host: "localhost:3000", origin: "https://evil.example.com" }),
    )
    expect(res?.status).toBe(403)
  })

  it("rejects an Origin that differs only by port", () => {
    const res = rejectForeignRequest(
      req({ host: "localhost:3000", origin: "http://localhost:4000" }),
    )
    expect(res?.status).toBe(403)
  })

  it("rejects the opaque Origin 'null' and malformed values", () => {
    expect(
      rejectForeignRequest(req({ host: "localhost:3000", origin: "null" }))?.status,
    ).toBe(403)
    expect(
      rejectForeignRequest(req({ host: "localhost:3000", origin: "not a url" }))?.status,
    ).toBe(403)
  })
})
