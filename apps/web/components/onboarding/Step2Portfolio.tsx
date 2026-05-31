"use client"
import { useState } from "react"

import { Input } from "@/components/ui/input"
import { WizardData } from "./Wizard"
import { WizardShell } from "./wizard-shell"

type Props = {
  data: WizardData
  setData: (updater: (prev: WizardData) => WizardData) => void
  onNext: () => void
  onBack: () => void
  step: 1 | 2 | 3 | 4
}

const splitCsv = (raw: string): string[] =>
  raw
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean)

export function Step2Portfolio({ data, setData, onNext, onBack, step }: Props) {
  const [tickersRaw, setTickersRaw] = useState<string>(data.tickers.join(", "))
  const [themesRaw, setThemesRaw] = useState<string>(data.themes.join(", "))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const tickers = splitCsv(tickersRaw)
  const themes = splitCsv(themesRaw)
  const canSubmit = tickers.length > 0

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      // The backend schema requires >=1 watch_sector. We synthesise a default
      // sector wrapping the same tickers so the wizard succeeds; the user
      // refines real sector mapping later from the sidebar.
      const payload = {
        portfolio: { tickers, themes },
        watch_sectors: [
          { sector: "Default", tickers, notes: null },
        ],
        geopolitical: { conflicts: [] },
        watch_events: [],
      }
      const res = await fetch("/api/config", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const text = await res.text()
        setError(`PUT /api/config failed (HTTP ${res.status}): ${text}`)
        return
      }
      setData((prev) => ({ ...prev, tickers, themes }))
      onNext()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error")
    } finally {
      setBusy(false)
    }
  }

  return (
    <WizardShell
      step={step}
      title="Portfolio basics"
      description="Comma-separated. You can edit watch sectors later."
      busy={busy}
      error={error}
      primaryLabel="Next"
      primaryDisabled={!canSubmit}
      onPrimary={submit}
      onBack={onBack}
    >
      <label className="block space-y-1">
        <span className="text-sm font-medium">Tickers</span>
        <Input
          value={tickersRaw}
          onChange={(e) => setTickersRaw(e.target.value)}
          placeholder="PLTR, NVDA, GOOGL"
          data-testid="tickers-input"
        />
        <span className="text-xs text-muted-foreground">
          At least one ticker is required.
        </span>
      </label>
      <label className="block space-y-1">
        <span className="text-sm font-medium">Themes</span>
        <Input
          value={themesRaw}
          onChange={(e) => setThemesRaw(e.target.value)}
          placeholder="AI規制, 半導体, 関税"
          data-testid="themes-input"
        />
      </label>
    </WizardShell>
  )
}
