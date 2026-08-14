import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { WorkspaceScreen } from "@/components/screens/WorkspaceScreen"

const readFileHandle = vi.fn()
const readFileHandleAsObjectURL = vi.fn()
const writeFileHandle = vi.fn()

vi.mock("@/lib/fsAccess", () => ({
  readFileHandle: (...args: unknown[]) => readFileHandle(...args),
  readFileHandleAsObjectURL: (...args: unknown[]) => readFileHandleAsObjectURL(...args),
  writeFileHandle: (...args: unknown[]) => writeFileHandle(...args),
  resolveWorkspaceLink: () => null,
}))

// Stable identity: WorkspaceScreen's load effect depends on `selected`, so a
// fresh object per render would re-trigger it forever. The real store memoizes.
let selectedFile: { path: string; handle: FileSystemFileHandle } | null = null

vi.mock("@/lib/workspaceStore", () => ({
  useWorkspaceState: () => ({
    selected: selectedFile,
    fileIndex: [],
    selectFile: vi.fn(),
  }),
}))

function renderWith(path: string) {
  selectedFile = { path, handle: {} as FileSystemFileHandle }
  return render(<WorkspaceScreen />)
}

beforeEach(() => {
  vi.clearAllMocks()
  readFileHandle.mockResolvedValue("decoded text")
  readFileHandleAsObjectURL.mockResolvedValue("blob:fake-url")
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:fake-url"),
    revokeObjectURL: vi.fn(),
  })
})

describe("WorkspaceScreen — PDF files", () => {
  it("renders the PDF in a frame instead of decoding it as text (success)", async () => {
    renderWith("docs/report.pdf")

    await waitFor(() => expect(screen.getByTestId("workspace-pdf")).toBeInTheDocument())
    expect(readFileHandleAsObjectURL).toHaveBeenCalledTimes(1)
  })

  it("never decodes a PDF as text — that is what produced the mojibake (failure)", async () => {
    renderWith("docs/report.pdf")

    await waitFor(() => expect(screen.getByTestId("workspace-pdf")).toBeInTheDocument())
    expect(readFileHandle).not.toHaveBeenCalled()
  })

  it("offers no editor or Save, so a PDF cannot be corrupted by saving (failure)", async () => {
    renderWith("docs/report.pdf")

    await waitFor(() => expect(screen.getByTestId("workspace-pdf")).toBeInTheDocument())
    expect(screen.queryByTestId("workspace-editor")).not.toBeInTheDocument()
    expect(screen.queryByTestId("workspace-save")).not.toBeInTheDocument()
  })
})

describe("WorkspaceScreen — binaries with no viewer", () => {
  it("shows an explicit non-previewable message rather than bytes (success)", async () => {
    renderWith("dist/bundle.zip")

    await waitFor(() =>
      expect(screen.getByTestId("workspace-binary-notice")).toBeInTheDocument(),
    )
  })

  it("reads neither as text nor as an object URL (boundary)", async () => {
    renderWith("dist/bundle.zip")

    await waitFor(() =>
      expect(screen.getByTestId("workspace-binary-notice")).toBeInTheDocument(),
    )
    expect(readFileHandle).not.toHaveBeenCalled()
    expect(readFileHandleAsObjectURL).not.toHaveBeenCalled()
  })

  it("offers no editor or Save (failure)", async () => {
    renderWith("dist/bundle.zip")

    await waitFor(() =>
      expect(screen.getByTestId("workspace-binary-notice")).toBeInTheDocument(),
    )
    expect(screen.queryByTestId("workspace-editor")).not.toBeInTheDocument()
    expect(screen.queryByTestId("workspace-save")).not.toBeInTheDocument()
  })
})

describe("WorkspaceScreen — text files keep working", () => {
  it("still decodes text and offers the editor and Save (regression guard)", async () => {
    renderWith("notes.txt")

    await waitFor(() => expect(screen.getByTestId("workspace-editor")).toBeInTheDocument())
    expect(readFileHandle).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId("workspace-save")).toBeInTheDocument()
  })
})

describe("WorkspaceScreen — object URL lifetime", () => {
  it("revokes the PDF object URL on unmount so the blob is not leaked (boundary)", async () => {
    const { unmount } = renderWith("docs/report.pdf")

    await waitFor(() => expect(screen.getByTestId("workspace-pdf")).toBeInTheDocument())
    unmount()

    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake-url")
  })
})
