"use client"

import { createContext, useContext, useMemo, useState } from "react"

// Shared selection state for the Workspace feature. The file tree renders in the
// global Sidebar rail while the editor/preview renders in the main area, so both
// need to agree on which file is selected — mirrors the Journal nav pattern.
type WorkspaceState = {
  selectedPath: string | null
  setSelectedPath: (path: string | null) => void
}

const WorkspaceContext = createContext<WorkspaceState | null>(null)

export function WorkspaceStateProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const value = useMemo(
    () => ({ selectedPath, setSelectedPath }),
    [selectedPath],
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
