"use client"
import { useEffect, useMemo, useState } from "react"

import { BriefingPanel } from "@/components/briefing/BriefingPanel"
import { BriefingRow } from "@/components/briefing/BriefingRow"
import { ALL_TAB, BriefingTabs } from "@/components/briefing/BriefingTabs"
import { useBriefingData } from "@/lib/hooks/useBriefingData"
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
  const [tab, setTab] = useState<string>(initialTab)

  // Persist the selected tab to the ?type= URL query.
  useEffect(() => {
    if (typeof window === "undefined") return
    const url = new URL(window.location.href)
    if (tab === ALL_TAB) url.searchParams.delete("type")
    else url.searchParams.set("type", tab)
    window.history.replaceState(null, "", url.toString())
  }, [tab])

  const visibleFiles = useMemo(
    () => (files ?? []).filter((f) => tab === ALL_TAB || f.type === tab),
    [files, tab],
  )

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
      {/* Records list */}
      <div
        data-testid="briefing-records-list"
        className={cn(
          "flex-shrink-0 overflow-y-auto border-r transition-all",
          selected && !fullSize ? "w-72" : "flex-1",
          fullSize && "hidden",
        )}
      >
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
