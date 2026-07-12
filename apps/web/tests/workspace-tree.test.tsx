import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { FileTree } from "@/components/workspace/FileTree"
import { WorkspaceStateProvider } from "@/lib/workspaceStore"

describe("FileTree", () => {
  it("renders the Open Folder button when no folder is open", () => {
    render(
      <WorkspaceStateProvider>
        <FileTree />
      </WorkspaceStateProvider>,
    )
    expect(screen.getByTestId("workspace-open-folder")).toHaveTextContent(
      "Open Folder",
    )
  })
})
