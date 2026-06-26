import { describe, expect, it } from "vitest"
import { SERVICES, serviceForPath } from "@/lib/services"

describe("SERVICES", () => {
  it("defines briefing first (fallback) and journal", () => {
    expect(SERVICES.map((s) => s.id)).toEqual(["briefing", "journal"])
    expect(SERVICES[0].defaultHref).toBe("/portfolio")
    expect(SERVICES[1].defaultHref).toBe("/journal")
  })

  it("briefing owns its six items, journal owns one", () => {
    const briefing = SERVICES.find((s) => s.id === "briefing")!
    expect(briefing.items.map((i) => i.href)).toEqual([
      "/portfolio", "/watch-sectors", "/geopolitical", "/run", "/chat", "/briefing",
    ])
    const journal = SERVICES.find((s) => s.id === "journal")!
    expect(journal.items.map((i) => i.href)).toEqual(["/journal"])
  })
})

describe("serviceForPath", () => {
  it.each([
    ["/portfolio", "briefing"],
    ["/watch-sectors", "briefing"],
    ["/geopolitical", "briefing"],
    ["/run", "briefing"],
    ["/chat", "briefing"],
    ["/briefing", "briefing"],
    ["/journal", "journal"],
  ])("maps %s to %s", (pathname, expected) => {
    expect(serviceForPath(pathname).id).toBe(expected)
  })

  it("matches nested routes by prefix", () => {
    expect(serviceForPath("/journal/2026-06-27").id).toBe("journal")
    expect(serviceForPath("/briefing/some-file.md").id).toBe("briefing")
  })

  it("falls back to briefing for unknown routes", () => {
    expect(serviceForPath("/config/usage").id).toBe("briefing")
    expect(serviceForPath("/auth").id).toBe("briefing")
    expect(serviceForPath("/totally-unknown").id).toBe("briefing")
  })
})
