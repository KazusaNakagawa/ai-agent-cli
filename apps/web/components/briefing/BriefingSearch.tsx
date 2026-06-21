import { useEffect, useRef, useState } from "react"

import { CloseIcon } from "./icons"

interface BriefingSearchProps {
  onSearch: (q: string) => void
  debounceMs?: number
}

/** Debounced search box over briefing name + body, with a clear button. */
export function BriefingSearch({ onSearch, debounceMs = 250 }: BriefingSearchProps) {
  const [value, setValue] = useState("")
  const onSearchRef = useRef(onSearch)
  onSearchRef.current = onSearch

  useEffect(() => {
    const id = setTimeout(() => onSearchRef.current(value.trim()), debounceMs)
    return () => clearTimeout(id)
  }, [value, debounceMs])

  return (
    <div className="relative flex items-center px-2 py-1">
      <input
        data-testid="briefing-search-input"
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search name or content…"
        aria-label="Search briefings"
        className="w-full rounded border bg-background px-2 py-1 pr-7 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
      />
      {value && (
        <button
          data-testid="briefing-search-clear"
          onClick={() => setValue("")}
          aria-label="Clear search"
          className="absolute right-3 rounded p-0.5 text-muted-foreground hover:text-foreground"
        >
          <CloseIcon />
        </button>
      )}
    </div>
  )
}
