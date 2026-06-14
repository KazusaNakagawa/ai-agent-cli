"use client"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { ChipInput } from "@/components/ChipInput"
import { SaveStatus } from "@/components/SaveStatus"
import { BriefingConfig } from "@/lib/config-types"
import { useConfigSave } from "@/lib/hooks/useConfigSave"

type Props = { initial: BriefingConfig }

const upper = (s: string) => s.toUpperCase()

export function PortfolioForm({ initial }: Props) {
  const [tickers, setTickers] = useState<string[]>(initial.portfolio.tickers)
  const [themes, setThemes] = useState<string[]>(initial.portfolio.themes)
  const { status, errors, genericError, save } = useConfigSave()

  const tickersError = errors.get("portfolio/tickers")
  const themesError = errors.get("portfolio/themes")

  const onSave = () =>
    save({ ...initial, portfolio: { tickers, themes } })

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <label className="text-sm font-medium" htmlFor="tickers">
          Tickers
        </label>
        <ChipInput
          values={tickers}
          onChange={setTickers}
          placeholder="PLTR, NVDA, GOOGL"
          ariaLabel="Tickers"
          normalise={upper}
          testid="tickers-chips"
        />
        {tickersError && (
          <p className="text-xs text-destructive" data-testid="tickers-error">
            {tickersError}
          </p>
        )}
      </div>
      <div className="space-y-1">
        <label className="text-sm font-medium" htmlFor="themes">
          Themes
        </label>
        <ChipInput
          values={themes}
          onChange={setThemes}
          placeholder="AI規制, 半導体, 関税"
          ariaLabel="Themes"
          testid="themes-chips"
        />
        {themesError && (
          <p className="text-xs text-destructive" data-testid="themes-error">
            {themesError}
          </p>
        )}
      </div>
      <div className="flex items-center gap-3">
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
