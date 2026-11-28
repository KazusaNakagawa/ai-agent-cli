import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ServiceTabs } from "@/components/ServiceTabs"
import { isDockerRuntime } from "@/lib/runtime"

vi.mock("next/navigation", () => ({ usePathname: () => "/portfolio" }))

describe("Docker badge (#627)", () => {
  it("is an icon with an accessible label in a container", () => {
    render(<ServiceTabs inDocker />)
    const badge = screen.getByTestId("runtime-badge")
    expect(badge).toHaveAttribute("title", "Running in Docker")
    expect(badge).toHaveTextContent("Running in Docker")
  })

  it("is absent on a native install", () => {
    render(<ServiceTabs />)
    expect(screen.queryByTestId("runtime-badge")).toBeNull()
  })

  it("reads the runtime marker exactly", () => {
    expect(isDockerRuntime({ BRIEF_LENS_RUNTIME: "docker" })).toBe(true)
    expect(isDockerRuntime({})).toBe(false)
    expect(isDockerRuntime({ BRIEF_LENS_RUNTIME: "" })).toBe(false)
    expect(isDockerRuntime({ BRIEF_LENS_RUNTIME: "native" })).toBe(false)
  })
})
