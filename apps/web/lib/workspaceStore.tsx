"use client"

import { createContext, useContext, useEffect, useMemo, useState } from "react"

// Shared state for the Workspace feature. The file tree (with its root picker)
// renders in the global Sidebar rail while the editor/preview renders in the
// main area, so both need to agree on the selected root + file — mirrors the
// Journal nav pattern.
type WorkspaceState = {
  rootId: string | null
  setRootId: (id: string) => void
  selectedPath: string | null
  setSelectedPath: (path: string | null) => void
}

const WorkspaceContext = createContext<WorkspaceState | null>(null)

const ROOT_STORAGE_KEY = "workspace.rootId"

export function WorkspaceStateProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [rootId, setRootIdState] = useState<string | null>(null)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  // Restore the last-used root from localStorage after mount (SSR-safe).
  useEffect(() => {
    try {
      const saved = localStorage.getItem(ROOT_STORAGE_KEY)
      if (saved) setRootIdState(saved)
    } catch {
      // localStorage unavailable (private mode / quota); default applies
    }
  }, [])

  // Switching root clears the current file selection — the path is only
  // meaningful relative to its root.
  const setRootId = (id: string) => {
    setRootIdState(id)
    setSelectedPath(null)
    try {
      localStorage.setItem(ROOT_STORAGE_KEY, id)
    } catch {
      // localStorage unavailable; selection still works for this session
    }
  }

  const value = useMemo(
    () => ({ rootId, setRootId, selectedPath, setSelectedPath }),
    [rootId, selectedPath],
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
