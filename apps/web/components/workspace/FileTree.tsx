"use client"

import { useCallback, useEffect, useState } from "react"

import { useWorkspaceState } from "@/lib/workspaceStore"

export type TreeEntry = {
  name: string
  path: string
  type: "dir" | "file"
}

type RootOption = { id: string; label: string }

async function fetchEntries(rootId: string, path: string): Promise<TreeEntry[]> {
  const params = new URLSearchParams({ root: rootId, path })
  const res = await fetch(`/api/workspace/tree?${params.toString()}`)
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { error?: string }
    throw new Error(body.error ?? `HTTP ${res.status}`)
  }
  const data = (await res.json()) as { entries: TreeEntry[] }
  return data.entries
}

function DirNode({
  rootId,
  entry,
  depth,
  selectedPath,
  onSelectFile,
}: {
  rootId: string
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
        setChildren(await fetchEntries(rootId, entry.path))
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load")
      }
    }
  }, [open, children, rootId, entry.path])

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
              rootId={rootId}
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
  rootId,
  entry,
  depth,
  selectedPath,
  onSelectFile,
}: {
  rootId: string
  entry: TreeEntry
  depth: number
  selectedPath: string | null
  onSelectFile: (path: string) => void
}) {
  if (entry.type === "dir") {
    return (
      <DirNode
        rootId={rootId}
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
  const { rootId, setRootId, selectedPath, setSelectedPath } = useWorkspaceState()
  const [roots, setRoots] = useState<RootOption[] | null>(null)
  const [entries, setEntries] = useState<TreeEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Load the configured roots once; pick the first as the default when the
  // store has no persisted selection.
  useEffect(() => {
    fetch("/api/workspace/roots")
      .then((res) => res.json())
      .then((data: { roots: RootOption[] }) => {
        setRoots(data.roots)
        if (rootId === null && data.roots.length > 0) {
          setRootId(data.roots[0].id)
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load roots"))
    // Run once on mount; setRootId only fills an empty selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // (Re)load the top-level entries whenever the active root changes.
  useEffect(() => {
    if (rootId === null) return
    setEntries(null)
    setError(null)
    fetchEntries(rootId, "")
      .then(setEntries)
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load"))
  }, [rootId])

  return (
    <div className="flex min-h-0 flex-col" data-testid="file-tree">
      {roots !== null && roots.length > 1 ? (
        <select
          value={rootId ?? ""}
          onChange={(e) => setRootId(e.target.value)}
          className="mb-2 w-full rounded border bg-background px-2 py-1 text-xs"
          data-testid="workspace-root-select"
          aria-label="Workspace root"
        >
          {roots.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label}
            </option>
          ))}
        </select>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {error !== null ? (
          <p className="p-2 text-xs text-destructive">{error}</p>
        ) : entries === null ? (
          <p className="p-2 text-xs text-muted-foreground">Loading…</p>
        ) : (
          entries.map((entry) => (
            <TreeRow
              key={entry.path}
              rootId={rootId as string}
              entry={entry}
              depth={0}
              selectedPath={selectedPath}
              onSelectFile={setSelectedPath}
            />
          ))
        )}
      </div>
    </div>
  )
}
