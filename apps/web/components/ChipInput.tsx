"use client"
import { KeyboardEvent, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"

type Props = {
  values: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  ariaLabel?: string
  // Optional value normaliser (e.g., uppercase for tickers). Applied at add-time.
  normalise?: (raw: string) => string
  // Optional testid prefix so each input on a page has a distinct hook.
  testid?: string
}

export function ChipInput({
  values,
  onChange,
  placeholder,
  ariaLabel,
  normalise,
  testid,
}: Props) {
  const [draft, setDraft] = useState("")

  const commit = (raw: string) => {
    const trimmed = (normalise ? normalise(raw) : raw).trim()
    if (!trimmed) return
    if (values.includes(trimmed)) {
      setDraft("")
      return
    }
    onChange([...values, trimmed])
    setDraft("")
  }

  const removeAt = (idx: number) => {
    onChange(values.filter((_, i) => i !== idx))
  }

  const handleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      commit(draft)
    } else if (e.key === "Backspace" && draft === "" && values.length > 0) {
      e.preventDefault()
      removeAt(values.length - 1)
    }
  }

  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-md border border-input bg-background px-2 py-1 text-sm"
      data-testid={testid}
    >
      {values.map((v, idx) => (
        <Badge
          key={`${v}-${idx}`}
          variant="secondary"
          className="flex items-center gap-1"
        >
          <span>{v}</span>
          <button
            type="button"
            aria-label={`Remove ${v}`}
            onClick={() => removeAt(idx)}
            className="rounded hover:bg-accent"
            data-testid={testid ? `${testid}-remove-${idx}` : undefined}
          >
            ×
          </button>
        </Badge>
      ))}
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKey}
        onBlur={() => commit(draft)}
        placeholder={values.length === 0 ? placeholder : undefined}
        aria-label={ariaLabel}
        className="h-7 flex-1 border-0 bg-transparent px-1 shadow-none focus-visible:ring-0"
        data-testid={testid ? `${testid}-draft` : undefined}
      />
    </div>
  )
}
