import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { Sidebar } from "@/components/Sidebar"
import { JobStateProvider } from "@/lib/jobStore"
import { JournalChatJobStateProvider } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider } from "@/lib/journalChatStore"
import { JournalNavProvider } from "@/lib/journalNavStore"
import { isDockerRuntime } from "@/lib/runtime"
import { WorkspaceStateProvider } from "@/lib/workspaceStore"

vi.mock("next/navigation", () => ({ usePathname: () => "/portfolio" }))

function renderSidebar(inDocker?: boolean) {
  return render(
    <JobStateProvider>
      <JournalChatStateProvider>
        <JournalChatJobStateProvider>
          <JournalNavProvider>
            <WorkspaceStateProvider>
              <Sidebar inDocker={inDocker} />
            </WorkspaceStateProvider>
          </JournalNavProvider>
        </JournalChatJobStateProvider>
      </JournalChatStateProvider>
    </JobStateProvider>,
  )
}

describe("Docker badge (#627)", () => {
  it("is shown in a container, labelled for the collapsed rail", () => {
    renderSidebar(true)
    const badge = screen.getByTestId("runtime-badge")
    expect(badge).toHaveTextContent("Docker")
    expect(badge).toHaveAttribute("title", "Running in Docker")
  })

  it("is absent on a native install", () => {
    renderSidebar()
    expect(screen.queryByTestId("runtime-badge")).toBeNull()
  })

  it("reads the runtime marker exactly", () => {
    expect(isDockerRuntime({ BRIEF_LENS_RUNTIME: "docker" })).toBe(true)
    expect(isDockerRuntime({})).toBe(false)
    expect(isDockerRuntime({ BRIEF_LENS_RUNTIME: "" })).toBe(false)
    expect(isDockerRuntime({ BRIEF_LENS_RUNTIME: "native" })).toBe(false)
  })
})
