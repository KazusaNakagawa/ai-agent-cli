"use client"

import { useEffect, useMemo, useRef, useState } from "react"

import { fuzzySearch } from "@/lib/fuzzy"
import { useWorkspaceState } from "@/lib/workspaceStore"

import { SearchIcon } from "./icons"

// VSCode-Quick-Open-style fuzzy file finder: a text input with a results
// pulldown, fuzzy-matched against the flat index built in workspaceStore.
export function FileFinder() {
  const { root, fileIndex, indexing, selectFile } = useWorkspaceState()
  const [query, setQuery] = useState("")
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const results = useMemo(
    () => fuzzySearch(fileIndex, query, (f) => f.path, 20),
    [fileIndex, query],
  )

  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("pointerdown", onPointerDown)
    return () => document.removeEventListener("pointerdown", onPointerDown)
  }, [])

  if (root === null) return null

  return (
    <div ref={containerRef} className="relative w-full max-w-md">
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          placeholder={indexing ? "Indexing…" : "Search files…"}
          className="w-full rounded border bg-background py-1.5 pl-8 pr-3 text-sm"
          data-testid="workspace-search-input"
        />
      </div>
      {open && results.length > 0 ? (
        <ul
          className="absolute z-10 mt-1 max-h-80 w-full overflow-y-auto rounded border bg-popover shadow-lg"
          data-testid="workspace-search-results"
        >
          {results.map((r) => (
            <li key={r.path}>
              <button
                type="button"
                onClick={() => {
                  selectFile(r)
                  setQuery("")
                  setOpen(false)
                }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent"
                data-testid={`workspace-search-result-${r.path}`}
              >
                <span className="truncate">{r.path.split("/").pop()}</span>
                <span className="truncate text-xs text-muted-foreground">{r.path}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
