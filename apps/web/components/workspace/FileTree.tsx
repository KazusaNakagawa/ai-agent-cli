"use client"

import { useCallback, useEffect, useState } from "react"

import { listChildren, type DirChild } from "@/lib/fsAccess"
import { useWorkspaceState } from "@/lib/workspaceStore"

import { ChevronIcon, FileIcon, FolderIcon } from "./icons"

function DirNode({
  entry,
  parentPath,
  depth,
}: {
  entry: DirChild
  parentPath: string
  depth: number
}) {
  const [open, setOpen] = useState(false)
  const [children, setChildren] = useState<DirChild[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const path = parentPath ? `${parentPath}/${entry.name}` : entry.name

  const toggle = useCallback(async () => {
    const next = !open
    setOpen(next)
    if (next && children === null) {
      try {
        setChildren(
          await listChildren(entry.handle as FileSystemDirectoryHandle),
        )
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load")
      }
    }
  }, [open, children, entry.handle])

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
            <TreeRow key={child.name} entry={child} parentPath={path} depth={depth + 1} />
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
      <FileIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="truncate">{entry.name}</span>
    </button>
  )
}

function TreeRow({
  entry,
  parentPath,
  depth,
}: {
  entry: DirChild
  parentPath: string
  depth: number
}) {
  return entry.kind === "directory" ? (
    <DirNode entry={entry} parentPath={parentPath} depth={depth} />
  ) : (
    <FileNode entry={entry} parentPath={parentPath} depth={depth} />
  )
}

export function FileTree() {
  const { root, rootName, needsReopen, openFolder } = useWorkspaceState()
  const [entries, setEntries] = useState<DirChild[] | null>(null)
  const [error, setError] = useState<string | null>(null)

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

      <div className="min-h-0 flex-1 overflow-y-auto">
        {error !== null ? (
          <p className="p-2 text-xs text-destructive">{error}</p>
        ) : root === null ? null : entries === null ? (
          <p className="p-2 text-xs text-muted-foreground">Loading…</p>
        ) : (
          entries.map((entry) => (
            <TreeRow key={entry.name} entry={entry} parentPath="" depth={0} />
          ))
        )}
      </div>
    </div>
  )
}
