"use client"
import { TrashIcon } from "@/components/briefing/icons"
import { useJournalNav } from "@/lib/journalNavStore"
import { cn } from "@/lib/utils"

/**
 * Journal entry list rendered inside the global Sidebar rail (below the
 * Journal/Config nav) when the Journal route is active. New/Trash controls sit
 * above the list; clicking an item opens its body in the main content area via
 * the shared JournalNav store.
 */
export function JournalSidebarList() {
  const {
    sortedEntries,
    entriesError,
    trash,
    showTrash,
    selected,
    trashPreview,
    loadEntry,
    loadTrashEntry,
    deleteEntry,
    restoreEntry,
    purgeEntry,
    toggleTrash,
    startCompose,
  } = useJournalNav()

  return (
    <section
      data-sidebar-section="journal"
      className="flex min-h-0 flex-1 flex-col gap-2"
    >
      {/* Top bar: New entry + Trash toggle */}
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={startCompose}
          className="flex flex-1 items-center justify-center gap-1 rounded-md border border-dashed px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          <span className="text-base leading-none">+</span> New
        </button>
        <button
          type="button"
          onClick={toggleTrash}
          aria-pressed={showTrash}
          className={cn(
            "flex items-center gap-1 rounded-md border px-3 py-2 text-xs font-medium transition-colors",
            showTrash
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
          )}
        >
          <TrashIcon /> Trash
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
      {entriesError && (
        <p className="px-1 py-2 text-xs text-destructive">{entriesError}</p>
      )}

      {showTrash ? (
        trash.length === 0 ? (
          <p className="px-1 py-2 text-xs text-muted-foreground">Trash is empty.</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {[...trash]
              .sort((a, b) => b.id.localeCompare(a.id))
              .map((e) => (
                <li key={e.id}>
                  <div
                    tabIndex={0}
                    role="button"
                    aria-label={`Preview trashed entry ${e.item || e.id}`}
                    onClick={() => void loadTrashEntry(e.id)}
                    onKeyDown={(ev) => {
                      if (ev.key === "Enter" || ev.key === " ") {
                        ev.preventDefault()
                        void loadTrashEntry(e.id)
                      }
                    }}
                    className={cn(
                      "group flex cursor-pointer items-center justify-between gap-2 rounded-md px-3 py-2 text-xs transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                      trashPreview === e.id
                        ? "bg-accent font-medium text-accent-foreground"
                        : "hover:bg-accent/50",
                    )}
                  >
                    <span className="truncate">{e.item || "—"}</span>
                    <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={(ev) => { ev.stopPropagation(); void restoreEntry(e.id) }}
                        className="rounded-md border px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                      >
                        Restore
                      </button>
                      <button
                        type="button"
                        onClick={(ev) => { ev.stopPropagation(); void purgeEntry(e.id) }}
                        className="rounded-md border px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </li>
              ))}
          </ul>
        )
      ) : sortedEntries.length === 0 ? (
        <p className="px-1 py-2 text-xs text-muted-foreground">No entries yet.</p>
      ) : (
        <ul className="flex flex-col gap-0.5">
          {sortedEntries.map((e) => (
            <li key={e.id}>
              <div
                tabIndex={0}
                role="button"
                aria-label={`Open entry ${e.item || e.id}`}
                onClick={() => void loadEntry(e.id)}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter" || ev.key === " ") {
                    ev.preventDefault()
                    void loadEntry(e.id)
                  }
                }}
                className={cn(
                  "group flex cursor-pointer items-center justify-between gap-2 rounded-md px-3 py-2 text-xs transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                  selected === e.id
                    ? "bg-accent font-medium text-accent-foreground"
                    : "hover:bg-accent/50",
                )}
              >
                <span className="truncate">{e.item || "—"}</span>
                <button
                  type="button"
                  onClick={(ev) => { ev.stopPropagation(); void deleteEntry(e.id) }}
                  aria-label={`Delete entry ${e.id}`}
                  className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-destructive focus:opacity-100 group-hover:opacity-100"
                >
                  <TrashIcon />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      </div>
    </section>
  )
}
