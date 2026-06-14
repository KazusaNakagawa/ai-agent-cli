"use client"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ChipInput } from "@/components/ChipInput"
import { SaveStatus } from "@/components/SaveStatus"
import { BriefingConfig, WatchSector } from "@/lib/config-types"
import { useConfigSave } from "@/lib/hooks/useConfigSave"

type Props = { initial: BriefingConfig }

const blankSector = (): WatchSector => ({ sector: "", tickers: [], notes: "" })
const upper = (s: string) => s.toUpperCase()

export function WatchSectorsForm({ initial }: Props) {
  const [rows, setRows] = useState<WatchSector[]>(initial.watch_sectors)
  const { status, errors, genericError, save } = useConfigSave()

  const collectionError = errors.get("watch_sectors")

  const updateRow = (idx: number, patch: Partial<WatchSector>) => {
    setRows((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)),
    )
  }
  const removeRow = (idx: number) => {
    setRows((prev) => prev.filter((_, i) => i !== idx))
  }
  const addRow = () => setRows((prev) => [...prev, blankSector()])

  const onSave = () =>
    save({
      ...initial,
      // Trim empty notes to null since the backend types `notes: str | None`.
      watch_sectors: rows.map((r) => ({
        ...r,
        notes: r.notes && r.notes.trim() !== "" ? r.notes : null,
      })),
    })

  return (
    <div className="space-y-4">
      {collectionError && (
        <p className="text-sm text-destructive" data-testid="collection-error">
          {collectionError}
        </p>
      )}
      <div className="space-y-3" data-testid="sector-rows">
        {rows.map((row, idx) => {
          const sectorErr = errors.get(`watch_sectors/${idx}/sector`)
          const tickersErr = errors.get(`watch_sectors/${idx}/tickers`)
          return (
            <Card key={idx}>
              <CardContent className="space-y-3 pt-6">
                <div className="space-y-1">
                  <label className="text-sm font-medium">Sector name</label>
                  <Input
                    value={row.sector}
                    onChange={(e) =>
                      updateRow(idx, { sector: e.target.value })
                    }
                    data-testid={`sector-name-${idx}`}
                  />
                  {sectorErr && (
                    <p className="text-xs text-destructive">{sectorErr}</p>
                  )}
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium">Tickers</label>
                  <ChipInput
                    values={row.tickers}
                    onChange={(tickers) => updateRow(idx, { tickers })}
                    normalise={upper}
                    placeholder="NVDA, MSFT"
                    ariaLabel={`Tickers for ${row.sector || "row " + (idx + 1)}`}
                    testid={`sector-tickers-${idx}`}
                  />
                  {tickersErr && (
                    <p className="text-xs text-destructive">{tickersErr}</p>
                  )}
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium">Notes</label>
                  <Input
                    value={row.notes ?? ""}
                    onChange={(e) => updateRow(idx, { notes: e.target.value })}
                    placeholder="Optional"
                    data-testid={`sector-notes-${idx}`}
                  />
                </div>
                <div className="flex justify-end">
                  <Button
                    variant="ghost"
                    onClick={() => removeRow(idx)}
                    data-testid={`sector-remove-${idx}`}
                  >
                    Delete
                  </Button>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>
      <div className="flex items-center gap-3">
        <Button variant="outline" onClick={addRow} data-testid="sector-add">
          + Add sector
        </Button>
        <Button onClick={() => void onSave()} disabled={status === "saving"}>
          Save
        </Button>
        <SaveStatus status={status} />
      </div>
      {genericError && (
        <p className="text-sm text-destructive" data-testid="generic-error">
          {genericError}
        </p>
      )}
    </div>
  )
}
