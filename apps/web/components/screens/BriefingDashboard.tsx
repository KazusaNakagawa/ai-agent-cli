"use client"
import { useEffect, useMemo, useState } from "react"

import { ArchiveButton } from "@/components/briefing/ArchiveButton"
import { BriefingPanel } from "@/components/briefing/BriefingPanel"
import { BriefingRow } from "@/components/briefing/BriefingRow"
import { BriefingSearch } from "@/components/briefing/BriefingSearch"
import { ALL_TAB, BriefingTabs } from "@/components/briefing/BriefingTabs"
import { ResizeHandle } from "@/components/ResizeHandle"
import { BriefingFile, BriefingListResponse } from "@/lib/briefing-types"
import { useBriefingData } from "@/lib/hooks/useBriefingData"
import { useResizable } from "@/lib/hooks/useResizable"
import { cn } from "@/lib/utils"

function initialTab(): string {
  if (typeof window === "undefined") return ALL_TAB
  return new URLSearchParams(window.location.search).get("type") ?? ALL_TAB
}

export function BriefingDashboard() {
  const {
    files,
    selected,
    content,
    loadingContent,
    listError,
    contentError,
    fetchContent,
    prefetch,
    close,
  } = useBriefingData()
  const [fullSize, setFullSize] = useState(false)
  const { width: listWidth, startResize } = useResizable({
    storageKey: "ai-agent:briefing-list-width:v1",
    defaultWidth: 288, // matches the previous fixed w-72
    minWidth: 200,
    maxWidth: 560,
  })
  const [tab, setTab] = useState<string>(initialTab)
  const [query, setQuery] = useState("")
  const [searchResults, setSearchResults] = useState<BriefingFile[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  // Persist the selected tab to the ?type= URL query.
  useEffect(() => {
    if (typeof window === "undefined") return
    const url = new URL(window.location.href)
    if (tab === ALL_TAB) url.searchParams.delete("type")
    else url.searchParams.set("type", tab)
    window.history.replaceState(null, "", url.toString())
  }, [tab])

  // Fetch server-side search results when the (debounced) query changes.
  useEffect(() => {
    if (query === "") {
      setSearchResults(null)
      setSearching(false)
      setSearchError(null)
      return
    }
    let cancelled = false
    setSearching(true)
    setSearchError(null)
    fetch(`/api/briefing/search?q=${encodeURIComponent(query)}`, { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data: BriefingListResponse) => {
        if (!cancelled) setSearchResults(data.files)
      })
      .catch((e) => {
        if (cancelled) return
        // Keep search errors distinct from a legitimate zero-result search.
        setSearchResults([])
        setSearchError(String(e))
      })
      .finally(() => {
        if (!cancelled) setSearching(false)
      })
    return () => {
      cancelled = true
    }
  }, [query])

  // Search (when active) and Type tab combine as an AND filter.
  const visibleFiles = useMemo(() => {
    const base = query !== "" ? (searchResults ?? []) : (files ?? [])
    return base.filter((f) => tab === ALL_TAB || f.type === tab)
  }, [files, tab, query, searchResults])

  const handleClose = () => {
    setFullSize(false)
    close()
  }

  if (listError) {
    return (
      <p data-testid="briefing-error" className="text-sm text-destructive">
        Failed to load briefings: {listError}
      </p>
    )
  }

  if (files === null) {
    return (
      <p data-testid="briefing-loading" className="text-sm text-muted-foreground">
        Loading briefings…
      </p>
    )
  }

  if (files.length === 0) {
    return (
      <p data-testid="briefing-empty" className="text-sm text-muted-foreground">
        No briefing files found.
      </p>
    )
  }

  return (
    <div data-testid="briefing-dashboard" className="flex h-full">
      {/* Records list (resizable when a file is open) */}
      <div
        data-testid="briefing-records-list"
        style={selected && !fullSize ? { width: listWidth } : undefined}
        className={cn(
          "relative flex-shrink-0 overflow-y-auto border-r",
          !(selected && !fullSize) && "flex-1",
          fullSize && "hidden",
        )}
      >
        <ArchiveButton />
        <BriefingSearch onSearch={setQuery} />
        <BriefingTabs files={files} selected={tab} onSelect={setTab} />
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Date</th>
              <th className="w-8 px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {visibleFiles.map((file) => (
              <BriefingRow
                key={file.name}
                file={file}
                selected={selected?.name === file.name}
                onOpen={fetchContent}
                onHover={prefetch}
              />
            ))}
          </tbody>
        </table>
        {searching && (
          <p
            data-testid="briefing-search-loading"
            className="px-3 py-2 text-xs text-muted-foreground"
          >
            Searching…
          </p>
        )}
        {!searching && searchError && (
          <p
            data-testid="briefing-search-error"
            className="px-3 py-2 text-xs text-destructive"
          >
            Search failed: {searchError}
          </p>
        )}
        {!searching && !searchError && visibleFiles.length === 0 && (
          <p
            data-testid="briefing-no-results"
            className="px-3 py-2 text-xs text-muted-foreground"
          >
            No matching briefings.
          </p>
        )}
        {selected && !fullSize && (
          <ResizeHandle
            onPointerDown={startResize}
            data-testid="briefing-list-resizer"
          />
        )}
      </div>

      {/* Side panel */}
      {selected && (
        <div className="min-w-0 flex-1 overflow-hidden">
          <BriefingPanel
            file={selected}
            content={content}
            loading={loadingContent}
            error={contentError}
            fullSize={fullSize}
            onToggleFullSize={() => setFullSize((v) => !v)}
            onClose={handleClose}
          />
        </div>
      )}
    </div>
  )
}
