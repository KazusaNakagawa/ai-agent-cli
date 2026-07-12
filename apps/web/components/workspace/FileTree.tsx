"use client"

import { useCallback, useEffect, useState } from "react"

import { colorForFile } from "@/lib/fileColors"
import { listChildren, SKIP_DIR_NAMES, type DirChild } from "@/lib/fsAccess"
import { useWorkspaceState } from "@/lib/workspaceStore"

import { ChevronIcon, CollapseAllIcon, ExpandAllIcon, FileIcon, FolderIcon } from "./icons"

// `expandGen`/`collapseGen` are monotonically increasing counters from the
// toolbar buttons. Each DirNode reacts to a change (including on its own
// mount, since children created while cascading a prior generation are born
// already "inside" that generation) — this is what makes expand/collapse
// apply recursively without a central registry of every open node.
type TreeSignal = { expandGen: number; collapseGen: number }

function DirNode({
  entry,
  parentPath,
  depth,
  signal,
}: {
  entry: DirChild
  parentPath: string
  depth: number
  signal: TreeSignal
}) {
  const [open, setOpen] = useState(false)
  const [children, setChildren] = useState<DirChild[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const path = parentPath ? `${parentPath}/${entry.name}` : entry.name

  const load = useCallback(async () => {
    try {
      setChildren(await listChildren(entry.handle as FileSystemDirectoryHandle))
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load")
    }
  }, [entry.handle])

  const toggle = useCallback(async () => {
    const next = !open
    setOpen(next)
    if (next && children === null) await load()
  }, [open, children, load])

  useEffect(() => {
    if (signal.expandGen === 0 || SKIP_DIR_NAMES.has(entry.name)) return
    setOpen(true)
    if (children === null) void load()
    // Re-run on every expand-all click (generation bump) and on mount for
    // nodes created while cascading a generation that's already > 0.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signal.expandGen])

  useEffect(() => {
    if (signal.collapseGen === 0) return
    setOpen(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signal.collapseGen])

  return (
    <div>
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-sm hover:bg-accent"
        style={{ paddingLeft: depth * 12 + 4 }}
        data-testid={`tree-dir-${path}`}
      >
        <ChevronIcon className="h-3 w-3 shrink-0 text-muted-foreground" open={open} />
        <FolderIcon className="h-4 w-4 shrink-0" />
        <span className="truncate">{entry.name}</span>
      </button>
      {open && error !== null ? (
        <p
          className="px-2 text-xs text-destructive"
          style={{ paddingLeft: depth * 12 + 20 }}
        >
          {error}
        </p>
      ) : null}
      {open && children !== null
        ? children.map((child) => (
            <TreeRow
              key={child.name}
              entry={child}
              parentPath={path}
              depth={depth + 1}
              signal={signal}
            />
          ))
        : null}
    </div>
  )
}

function FileNode({
  entry,
  parentPath,
  depth,
}: {
  entry: DirChild
  parentPath: string
  depth: number
}) {
  const { selected, selectFile } = useWorkspaceState()
  const path = parentPath ? `${parentPath}/${entry.name}` : entry.name
  const active = selected?.path === path
  return (
    <button
      type="button"
      onClick={() =>
        selectFile({ handle: entry.handle as FileSystemFileHandle, path })
      }
      className={`flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-sm hover:bg-accent ${
        active ? "bg-accent font-medium" : ""
      }`}
      style={{ paddingLeft: depth * 12 + 20 }}
      data-testid={`tree-file-${path}`}
    >
      <FileIcon className="h-4 w-4 shrink-0" color={colorForFile(entry.name)} />
      <span className="truncate">{entry.name}</span>
    </button>
  )
}

function TreeRow({
  entry,
  parentPath,
  depth,
  signal,
}: {
  entry: DirChild
  parentPath: string
  depth: number
  signal: TreeSignal
}) {
  return entry.kind === "directory" ? (
    <DirNode entry={entry} parentPath={parentPath} depth={depth} signal={signal} />
  ) : (
    <FileNode entry={entry} parentPath={parentPath} depth={depth} />
  )
}

export function FileTree() {
  const { root, rootName, needsReopen, openFolder } = useWorkspaceState()
  const [entries, setEntries] = useState<DirChild[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandGen, setExpandGen] = useState(0)
  const [collapseGen, setCollapseGen] = useState(0)

  useEffect(() => {
    if (root === null) {
      setEntries(null)
      return
    }
    setError(null)
    listChildren(root)
      .then(setEntries)
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load"))
  }, [root])

  return (
    <div className="flex min-h-0 flex-col" data-testid="file-tree">
      <button
        type="button"
        onClick={() => void openFolder()}
        className="mb-2 flex items-center gap-1.5 rounded border px-2 py-1 text-xs hover:bg-accent"
        data-testid="workspace-open-folder"
      >
        <FolderIcon className="h-4 w-4" />
        {root !== null ? (
          <span className="truncate" title={rootName ?? undefined}>
            {rootName}
          </span>
        ) : (
          "Open Folder…"
        )}
      </button>

      {needsReopen && root === null ? (
        <p className="px-1 text-xs text-muted-foreground">
          Reopen the folder to grant access again.
        </p>
      ) : null}

      {root !== null ? (
        <div className="mb-1 flex items-center justify-end gap-1">
          <button
            type="button"
            onClick={() => setExpandGen((g) => g + 1)}
            title="Expand all"
            aria-label="Expand all"
            data-testid="workspace-expand-all"
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <ExpandAllIcon className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setCollapseGen((g) => g + 1)}
            title="Collapse all"
            aria-label="Collapse all"
            data-testid="workspace-collapse-all"
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <CollapseAllIcon className="h-3.5 w-3.5" />
          </button>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {error !== null ? (
          <p className="p-2 text-xs text-destructive">{error}</p>
        ) : root === null ? null : entries === null ? (
          <p className="p-2 text-xs text-muted-foreground">Loading…</p>
        ) : (
          entries.map((entry) => (
            <TreeRow
              key={entry.name}
              entry={entry}
              parentPath=""
              depth={0}
              signal={{ expandGen, collapseGen }}
            />
          ))
        )}
      </div>
    </div>
  )
}
