"use client"

import { createContext, useContext, useEffect, useMemo, useState } from "react"

import {
  ensureReadWrite,
  loadRootHandle,
  pickDirectory,
  saveRootHandle,
} from "@/lib/fsAccess"

// Shared state for the Workspace feature. The file tree (rooted at a
// user-picked local folder) renders in the global Sidebar rail while the
// editor/preview renders in the main area, so both agree on the open folder and
// selected file. Backed by the File System Access API — no server involvement.
export type SelectedFile = {
  handle: FileSystemFileHandle
  // Slash-joined path relative to the root, for display + identity.
  path: string
}

type WorkspaceState = {
  root: FileSystemDirectoryHandle | null
  rootName: string | null
  /** True when a folder was restored from a previous session but needs the
   *  user to re-grant permission (a user gesture) before it can be read. */
  needsReopen: boolean
  openFolder: () => Promise<void>
  selected: SelectedFile | null
  selectFile: (file: SelectedFile) => void
}

const WorkspaceContext = createContext<WorkspaceState | null>(null)

export function WorkspaceStateProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [root, setRoot] = useState<FileSystemDirectoryHandle | null>(null)
  const [needsReopen, setNeedsReopen] = useState(false)
  const [selected, setSelected] = useState<SelectedFile | null>(null)

  // Restore the last-opened folder after a reload. queryPermission (inside
  // ensureReadWrite via the granted path) needs no gesture; if it's only
  // "prompt", surface a reopen affordance instead of silently failing.
  useEffect(() => {
    let cancelled = false
    loadRootHandle().then(async (handle) => {
      if (cancelled || handle === null) return
      const granted = (await handle.queryPermission?.({ mode: "readwrite" })) === "granted"
      if (granted) {
        setRoot(handle)
      } else {
        setNeedsReopen(true)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  const openFolder = async () => {
    const handle = await pickDirectory()
    if (!(await ensureReadWrite(handle))) return
    await saveRootHandle(handle)
    setRoot(handle)
    setNeedsReopen(false)
    setSelected(null)
  }

  const value = useMemo(
    () => ({
      root,
      rootName: root?.name ?? null,
      needsReopen,
      openFolder,
      selected,
      selectFile: setSelected,
    }),
    [root, needsReopen, selected],
  )
  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspaceState(): WorkspaceState {
  const ctx = useContext(WorkspaceContext)
  if (ctx === null) {
    throw new Error(
      "useWorkspaceState must be used within a WorkspaceStateProvider",
    )
  }
  return ctx
}
