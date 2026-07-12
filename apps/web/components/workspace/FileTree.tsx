"use client"

import { useCallback, useEffect, useState } from "react"

import { useWorkspaceState } from "@/lib/workspaceStore"

export type TreeEntry = {
  name: string
  path: string
  type: "dir" | "file"
}

async function fetchEntries(path: string): Promise<TreeEntry[]> {
  const res = await fetch(`/api/workspace/tree?path=${encodeURIComponent(path)}`)
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { error?: string }
    throw new Error(body.error ?? `HTTP ${res.status}`)
  }
  const data = (await res.json()) as { entries: TreeEntry[] }
  return data.entries
}

function DirNode({
  entry,
  depth,
  selectedPath,
  onSelectFile,
}: {
  entry: TreeEntry
  depth: number
  selectedPath: string | null
  onSelectFile: (path: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [children, setChildren] = useState<TreeEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const toggle = useCallback(async () => {
    const next = !open
    setOpen(next)
    if (next && children === null) {
      try {
        setChildren(await fetchEntries(entry.path))
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load")
      }
    }
  }, [open, children, entry.path])

  return (
    <div>
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-sm hover:bg-accent"
        style={{ paddingLeft: depth * 12 + 4 }}
        data-testid={`tree-dir-${entry.path}`}
      >
        <span className="text-muted-foreground">{open ? "▾" : "▸"}</span>
        <span>📁 {entry.name}</span>
      </button>
      {open && error !== null ? (
        <p className="px-2 text-xs text-destructive" style={{ paddingLeft: depth * 12 + 16 }}>
          {error}
        </p>
      ) : null}
      {open && children !== null
        ? children.map((child) => (
            <TreeRow
              key={child.path}
              entry={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelectFile={onSelectFile}
            />
          ))
        : null}
    </div>
  )
}

function TreeRow({
  entry,
  depth,
  selectedPath,
  onSelectFile,
}: {
  entry: TreeEntry
  depth: number
  selectedPath: string | null
  onSelectFile: (path: string) => void
}) {
  if (entry.type === "dir") {
    return (
      <DirNode
        entry={entry}
        depth={depth}
        selectedPath={selectedPath}
        onSelectFile={onSelectFile}
      />
    )
  }
  const active = entry.path === selectedPath
  return (
    <button
      type="button"
      onClick={() => onSelectFile(entry.path)}
      className={`flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-sm hover:bg-accent ${
        active ? "bg-accent font-medium" : ""
      }`}
      style={{ paddingLeft: depth * 12 + 16 }}
      data-testid={`tree-file-${entry.path}`}
    >
      📄 {entry.name}
    </button>
  )
}

export function FileTree() {
  const { selectedPath, setSelectedPath } = useWorkspaceState()
  const onSelectFile = setSelectedPath
  const [roots, setRoots] = useState<TreeEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchEntries("")
      .then(setRoots)
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load"))
  }, [])

  if (error !== null) {
    return <p className="p-2 text-xs text-destructive">{error}</p>
  }
  if (roots === null) {
    return <p className="p-2 text-xs text-muted-foreground">Loading…</p>
  }
  return (
    <div data-testid="file-tree">
      {roots.map((entry) => (
        <TreeRow
          key={entry.path}
          entry={entry}
          depth={0}
          selectedPath={selectedPath}
          onSelectFile={onSelectFile}
        />
      ))}
    </div>
  )
}
