"use client"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ChipInput } from "@/components/ChipInput"
import { SaveStatus } from "@/components/SaveStatus"
import { BriefingConfig, Conflict } from "@/lib/config-types"
import { useConfigSave } from "@/lib/hooks/useConfigSave"

type Props = { initial: BriefingConfig }

const blankConflict = (): Conflict => ({
  name: "",
  affected_sectors: [],
  related_tickers: [],
  notes: "",
})
const upper = (s: string) => s.toUpperCase()

export function GeopoliticalForm({ initial }: Props) {
  const [rows, setRows] = useState<Conflict[]>(initial.geopolitical.conflicts)
  const { status, errors, genericError, save } = useConfigSave()

  const updateRow = (idx: number, patch: Partial<Conflict>) =>
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)))
  const removeRow = (idx: number) =>
    setRows((prev) => prev.filter((_, i) => i !== idx))
  const addRow = () => setRows((prev) => [...prev, blankConflict()])

  const onSave = () =>
    save({
      ...initial,
      geopolitical: {
        conflicts: rows.map((r) => ({
          ...r,
          notes: r.notes && r.notes.trim() !== "" ? r.notes : null,
        })),
      },
    })

  return (
    <div className="space-y-4">
      <div className="space-y-3" data-testid="conflict-rows">
        {rows.map((row, idx) => {
          const nameErr = errors.get(`geopolitical/conflicts/${idx}/name`)
          const sectorsErr = errors.get(
            `geopolitical/conflicts/${idx}/affected_sectors`,
          )
          return (
            <Card key={idx}>
              <CardContent className="space-y-3 pt-6">
                <div className="space-y-1">
                  <label className="text-sm font-medium">Name</label>
                  <Input
                    value={row.name}
                    onChange={(e) => updateRow(idx, { name: e.target.value })}
                    placeholder="中東 (米イスラエル vs イラン)"
                    data-testid={`conflict-name-${idx}`}
                  />
                  {nameErr && (
                    <p className="text-xs text-destructive">{nameErr}</p>
                  )}
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium">
                    Affected sectors
                  </label>
                  <ChipInput
                    values={row.affected_sectors}
                    onChange={(affected_sectors) =>
                      updateRow(idx, { affected_sectors })
                    }
                    placeholder="エネルギー, 防衛"
                    testid={`conflict-sectors-${idx}`}
                  />
                  {sectorsErr && (
                    <p className="text-xs text-destructive">{sectorsErr}</p>
                  )}
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium">
                    Related tickers
                  </label>
                  <ChipInput
                    values={row.related_tickers}
                    onChange={(related_tickers) =>
                      updateRow(idx, { related_tickers })
                    }
                    normalise={upper}
                    placeholder="XOM, LMT"
                    testid={`conflict-tickers-${idx}`}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium">Notes</label>
                  <Input
                    value={row.notes ?? ""}
                    onChange={(e) =>
                      updateRow(idx, { notes: e.target.value })
                    }
                    placeholder="Optional"
                    data-testid={`conflict-notes-${idx}`}
                  />
                </div>
                <div className="flex justify-end">
                  <Button
                    variant="ghost"
                    onClick={() => removeRow(idx)}
                    data-testid={`conflict-remove-${idx}`}
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
        <Button variant="outline" onClick={addRow} data-testid="conflict-add">
          + Add conflict
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
